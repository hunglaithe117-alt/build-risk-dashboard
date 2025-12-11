#!/bin/bash
# Script to generate PNG from PlantUML diagrams
# Usage: ./generate_diagrams.sh

# Color codes for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}PlantUML Diagram Generator${NC}"
echo "================================"

# Check if plantuml is installed
if ! command -v plantuml &> /dev/null; then
    echo "Error: plantuml is not installed"
    echo "Install with: brew install plantuml (Mac) or apt-get install plantuml (Linux)"
    exit 1
fi

# Create output directory if it doesn't exist
mkdir -p Figure/diagrams

# Define diagram files
DIAGRAMS=(
    "diagrams/use_case_general.puml"
    "diagrams/activity_flow1_repository.puml"
    "diagrams/activity_flow2_dataset_enrichment.puml"
    "diagrams/activity_build_risk_evaluation.puml"
)

# Generate PNG for each diagram
for diagram in "${DIAGRAMS[@]}"; do
    if [ -f "$diagram" ]; then
        echo -e "${BLUE}Generating: $diagram${NC}"
        
        # Extract filename without extension
        filename=$(basename "$diagram" .puml)
        
        # Generate PNG
        plantuml -png -o ../Figure/diagrams "$diagram"
        
        if [ $? -eq 0 ]; then
            echo -e "${GREEN}✓ Generated: Figure/diagrams/${filename}.png${NC}"
        else
            echo "✗ Failed to generate: $diagram"
        fi
    else
        echo "✗ File not found: $diagram"
    fi
done

echo ""
echo -e "${GREEN}All diagrams generated successfully!${NC}"
echo ""
echo "Next steps:"
echo "1. Check Figure/diagrams/ for generated PNG files"
echo "2. Add these references to your LaTeX file:"
echo ""
echo '   \includegraphics[width=0.8\textwidth]{Figure/diagrams/use_case_general.png}'
echo '   \includegraphics[width=0.85\textwidth]{Figure/diagrams/activity_flow1_repository.png}'
echo '   \includegraphics[width=0.85\textwidth]{Figure/diagrams/activity_flow2_dataset_enrichment.png}'
echo '   \includegraphics[width=0.85\textwidth]{Figure/diagrams/activity_build_risk_evaluation.png}'
