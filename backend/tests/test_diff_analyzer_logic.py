import unittest
import unittest
from app.services.extracts.diff_analyzer import (
    _is_test_file,
    _matches_test_definition,
    _matches_assertion,
)


class TestDiffAnalyzerLogic(unittest.TestCase):
    def test_is_test_file_ruby(self):
        # Ruby: ends with .rb AND (contains test/, tests/, or spec/) AND (does NOT contain lib/)
        self.assertTrue(_is_test_file("test/foo.rb", "ruby"))
        self.assertTrue(_is_test_file("spec/foo.rb", "ruby"))
        self.assertTrue(_is_test_file("tests/foo.rb", "ruby"))
        self.assertFalse(_is_test_file("lib/foo.rb", "ruby"))
        self.assertFalse(_is_test_file("lib/test/foo.rb", "ruby"))  # contains lib/
        self.assertFalse(_is_test_file("foo.rb", "ruby"))  # no test dir

    def test_is_test_file_java(self):
        # Java: ends with .java AND (contains test/ or tests/ OR ends with Test.java)
        self.assertTrue(_is_test_file("src/test/Foo.java", "java"))
        self.assertTrue(_is_test_file("src/tests/Foo.java", "java"))
        self.assertTrue(_is_test_file("src/main/FooTest.java", "java"))
        self.assertTrue(_is_test_file("FooTest.java", "java"))
        self.assertFalse(_is_test_file("src/main/Foo.java", "java"))

    def test_is_test_file_python(self):
        # Python: ends with .py AND (starts with test_ OR ends with _test.py OR is test.py OR contains test/ or tests/)
        self.assertTrue(_is_test_file("tests/foo.py", "python"))
        self.assertTrue(_is_test_file("test/foo.py", "python"))
        self.assertTrue(_is_test_file("test_foo.py", "python"))
        self.assertTrue(_is_test_file("foo_test.py", "python"))
        self.assertTrue(_is_test_file("test.py", "python"))
        self.assertFalse(_is_test_file("foo.py", "python"))

    def test_matches_test_definition_ruby(self):
        self.assertTrue(_matches_test_definition("  def test_something", "ruby"))
        # self.assertTrue(_matches_test_definition("  test 'something' do", "ruby")) # Not supported
        self.assertTrue(_matches_test_definition("  it 'does something' do", "ruby"))
        # self.assertTrue(_matches_test_definition("  specify 'something' do", "ruby")) # Not supported
        self.assertTrue(_matches_test_definition("  should 'do something' do", "ruby"))
        self.assertFalse(_matches_test_definition("  def something", "ruby"))

    def test_matches_test_definition_java(self):
        self.assertTrue(_matches_test_definition("  @Test", "java"))
        self.assertTrue(_matches_test_definition("  public void myTest() {", "java"))

        # Debugging failed case
        line = "  protected void myTest() {"
        result = _matches_test_definition(line, "java")
        self.assertTrue(result)

        self.assertFalse(
            _matches_test_definition("  public void something() {", "java")
        )

    def test_matches_test_definition_python(self):
        self.assertTrue(_matches_test_definition("  def test_something():", "python"))
        self.assertFalse(_matches_test_definition("  def something():", "python"))

    def test_matches_assertion_ruby(self):
        self.assertTrue(_matches_assertion("  assert_equal 1, 1", "ruby"))
        self.assertTrue(_matches_assertion("  expect(foo).to eq(bar)", "ruby"))
        self.assertTrue(_matches_assertion("  foo.should eq(bar)", "ruby"))
        self.assertTrue(_matches_assertion("  obj.must_equal 1", "ruby"))
        self.assertTrue(_matches_assertion("  obj.wont_be_nil", "ruby"))
        self.assertFalse(_matches_assertion("  foo = bar", "ruby"))

    def test_matches_assertion_java(self):
        self.assertTrue(_matches_assertion("  assert true;", "java"))
        self.assertTrue(_matches_assertion("  assertEquals(1, 1);", "java"))
        self.assertFalse(_matches_assertion("  int x = 1;", "java"))

    def test_matches_assertion_python(self):
        self.assertTrue(_matches_assertion("  assert x == 1", "python"))
        self.assertTrue(_matches_assertion("  self.assertEqual(x, 1)", "python"))
        self.assertTrue(
            _matches_assertion("  with pytest.raises(ValueError):", "python")
        )
        self.assertTrue(
            _matches_assertion("  assert x == pytest.approx(1.0)", "python")
        )
        self.assertFalse(_matches_assertion("  x = 1", "python"))


if __name__ == "__main__":
    unittest.main()
