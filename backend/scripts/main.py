import os
import shutil
import sqlite3
import time
import yaml
import requests
from dotenv import load_dotenv
from git import Repo

# Tải cấu hình từ file .env
load_dotenv()


class EnvConfigurableReconstructor:
    def __init__(self):
        # 1. Khởi tạo cấu hình từ biến môi trường
        self.token = os.getenv("GITHUB_TOKEN")
        self.repo_name = os.getenv("REPO_FULL_NAME")
        self.src_path = os.getenv("SOURCE_REPO_PATH")
        self.dst_path = os.getenv("TARGET_REPO_PATH")

        # Chuyển đổi limit sang số nguyên, mặc định là None (toàn bộ)
        limit_val = os.getenv("LIMIT_COMMITS")
        self.limit = int(limit_val) if limit_val and int(limit_val) > 0 else None

        self.poll_interval = int(os.getenv("POLL_INTERVAL", 30))
        self.workflow_timeout = int(
            os.getenv("WORKFLOW_TIMEOUT", 600)
        )  # Default 10 minutes
        self.headers = {"Authorization": f"token {self.token}"}

        # 2. Khởi tạo trạng thái và Repo
        self.db = sqlite3.connect("state.db")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS mapping (src TEXT PRIMARY KEY, dst TEXT, status TEXT)"
        )
        self.src_repo = Repo(self.src_path)
        self.dst_repo = Repo(self.dst_path)

    def reconstruct(self):
        # Sử dụng topo-order để bảo toàn quan hệ cha-con [cite: 33, 42]
        all_commits = list(self.src_repo.iter_commits(topo_order=True, reverse=True))

        # Áp dụng tham số mô phỏng N commit mới nhất
        target_commits = all_commits[-self.limit :] if self.limit else all_commits
        print(f"Bắt đầu tái tạo {len(target_commits)} commit...")

        for commit in target_commits:
            if self.db.execute(
                "SELECT 1 FROM mapping WHERE src=?", (commit.hexsha,)
            ).fetchone():
                continue

            # Snapshot transfer: checkout source commit and copy files to destination
            self.src_repo.git.checkout(commit.hexsha, force=True)

            # Clear destination working directory (except .git)
            for item in os.listdir(self.dst_path):
                if item == ".git":
                    continue
                item_path = os.path.join(self.dst_path, item)
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path)
                else:
                    os.remove(item_path)

            # Copy all files from source to destination
            for item in os.listdir(self.src_path):
                if item == ".git":
                    continue
                src_item = os.path.join(self.src_path, item)
                dst_item = os.path.join(self.dst_path, item)
                if os.path.isdir(src_item):
                    shutil.copytree(src_item, dst_item)
                else:
                    shutil.copy2(src_item, dst_item)

            # Stage all changes
            self.dst_repo.git.add("--all")

            # Làm sạch Workflow và tạo commit với metadata gốc [cite: 81]
            self._process_workflow_files(commit.hexsha)

            new_sha = self._create_plumbing_commit(commit)

            # Đẩy lên remote và giám sát CI/CD [cite: 86, 96]
            self.dst_repo.git.push("origin", f"{new_sha}:refs/heads/main", force=True)

            # Check if repo has workflows before waiting
            workflows_path = os.path.join(self.dst_path, ".github", "workflows")
            has_workflows = (
                os.path.exists(workflows_path)
                and any(
                    f.endswith((".yml", ".yaml")) for f in os.listdir(workflows_path)
                )
                if os.path.exists(workflows_path)
                else False
            )

            if has_workflows:
                status = self._wait_for_github_actions(new_sha)
            else:
                print(f"  Không có workflow, bỏ qua việc chờ CI...")
                status = "no_workflow"

            self.db.execute(
                "INSERT INTO mapping VALUES (?, ?, ?)", (commit.hexsha, new_sha, status)
            )
            self.db.commit()
            print(f"Commit {new_sha} hoàn tất với trạng thái: {status}")

    def _create_plumbing_commit(self, src_commit):
        """Tạo đối tượng commit bảo toàn thời gian gốc [cite: 78, 81]"""
        new_parents = []
        for p in src_commit.parents:
            res = self.db.execute(
                "SELECT dst FROM mapping WHERE src=?", (p.hexsha,)
            ).fetchone()
            if res:
                new_parents.append(self.dst_repo.commit(res[0]))

        # Nối vào lịch sử hiện tại nếu là điểm bắt đầu của limit
        if not new_parents and list(self.dst_repo.heads):
            new_parents.append(self.dst_repo.head.commit)

        return self.dst_repo.index.commit(
            src_commit.message,
            parent_commits=new_parents,
            author=src_commit.author,
            committer=src_commit.committer,
            author_date=src_commit.authored_datetime,
            commit_date=src_commit.committed_datetime,
            skip_hooks=True,
        ).hexsha

    def _wait_for_github_actions(self, sha):
        """Giám sát trạng thái CI/CD từ API với timeout [cite: 93, 98]"""
        url = (
            f"https://api.github.com/repos/{self.repo_name}/actions/runs?head_sha={sha}"
        )
        start_time = time.time()

        while True:
            elapsed = time.time() - start_time
            if elapsed > self.workflow_timeout:
                print(f"  ⚠️ Timeout sau {self.workflow_timeout}s, tiếp tục...")
                return "timeout"

            resp = requests.get(url, headers=self.headers)
            if resp.status_code == 200:
                runs = resp.json().get("workflow_runs", [])
                if not runs:
                    # No workflow runs found yet, wait a bit longer
                    print(f"  Đang chờ workflow bắt đầu... ({int(elapsed)}s)")
                elif all(r["status"] == "completed" for r in runs):
                    return runs[0]["conclusion"]
                else:
                    in_progress = sum(1 for r in runs if r["status"] != "completed")
                    print(
                        f"  Đang chờ {in_progress} workflow hoàn thành... ({int(elapsed)}s)"
                    )
            else:
                print(f"  API error: {resp.status_code}, retrying...")

            time.sleep(self.poll_interval)

    def _process_workflow_files(self, commit_sha):
        """Lọc bỏ các job không liên quan đến test, giữ lại các job test đơn giản"""
        workflows_path = os.path.join(self.dst_path, ".github", "workflows")

        if not os.path.exists(workflows_path):
            return

        # Whitelist: Các từ khóa để nhận diện job test (CHỈ giữ lại các job này)
        test_keywords = [
            "test",
            "lint",
            "check",
            "build",
            "ci",
            "validate",
            "verify",
            "unit",
            "integration",
            "format",
            "style",
        ]

        # Blacklist: Các bot, tool và action không phù hợp để replay (deploy, release, notify)
        bot_keywords = [
            "dependabot",
            "renovate",
            "snyk",
            "codecov",
            "sonar",
            "coveralls",
            "codacy",
            "deepsource",
            "bot",
            "deploy",
            "publish",
            "release",
            "push",
            "upload",
            "notify",
            "slack",
            "discord",
            "email",
            "schedule",
            "cron",
            "registry",
            "docker",
            "npm",
            "pypi",
            "pages",
        ]

        for filename in os.listdir(workflows_path):
            if not filename.endswith((".yml", ".yaml")):
                continue

            filepath = os.path.join(workflows_path, filename)

            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    workflow = yaml.safe_load(f)

                if not workflow or "jobs" not in workflow:
                    continue

                # Lọc job: chỉ giữ lại job test và không phải bot
                jobs_to_remove = []
                for job_name, job_config in workflow["jobs"].items():
                    job_name_lower = job_name.lower()
                    job_display_name = ""
                    if isinstance(job_config, dict) and "name" in job_config:
                        job_display_name = str(job_config["name"]).lower()

                    # Kiểm tra nếu là bot - loại bỏ
                    if any(
                        bot in job_name_lower or bot in job_display_name
                        for bot in bot_keywords
                    ):
                        jobs_to_remove.append(job_name)
                        continue

                    # Kiểm tra nếu job sử dụng secrets - loại bỏ
                    if isinstance(job_config, dict):
                        job_str = str(job_config).lower()
                        if "${{ secrets." in job_str or "secrets." in job_str:
                            jobs_to_remove.append(job_name)
                            continue

                    # Chỉ giữ lại job có liên quan đến test
                    is_test_job = any(
                        kw in job_name_lower or kw in job_display_name
                        for kw in test_keywords
                    )
                    if not is_test_job:
                        jobs_to_remove.append(job_name)

                # Xóa các job không phù hợp
                for job_name in jobs_to_remove:
                    del workflow["jobs"][job_name]
                    print(f"  Đã xóa job '{job_name}' từ {filename}")

                # Cập nhật 'needs' trong các job còn lại
                for job_name, job_config in workflow["jobs"].items():
                    if isinstance(job_config, dict) and "needs" in job_config:
                        needs = job_config["needs"]
                        if isinstance(needs, list):
                            job_config["needs"] = [
                                n for n in needs if n not in jobs_to_remove
                            ]
                            if not job_config["needs"]:
                                del job_config["needs"]
                        elif isinstance(needs, str) and needs in jobs_to_remove:
                            del job_config["needs"]

                # Nếu không còn job nào, xóa file workflow
                if not workflow["jobs"]:
                    os.remove(filepath)
                    print(f"  Đã xóa workflow file {filename} (không còn job)")
                else:
                    # Ghi lại file workflow đã được lọc
                    with open(filepath, "w", encoding="utf-8") as f:
                        yaml.dump(
                            workflow,
                            f,
                            default_flow_style=False,
                            allow_unicode=True,
                            sort_keys=False,
                        )

            except Exception as e:
                print(f"  Lỗi xử lý {filename}: {e}")

        # Stage lại các thay đổi workflow
        self.dst_repo.git.add("--all")


if __name__ == "__main__":
    reconstructor = EnvConfigurableReconstructor()
    reconstructor.reconstruct()
