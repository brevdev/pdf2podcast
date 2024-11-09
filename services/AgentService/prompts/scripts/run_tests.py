# prompts/scripts/run_tests.py
import argparse
import subprocess
from pathlib import Path
from typing import List, Optional

class PromptTestRunner:
    def __init__(self, config_dir: str = "configs"):
        self.base_dir = Path(__file__).parent.parent  # prompts directory
        self.config_dir = self.base_dir / config_dir
        self.outputs_dir = self.base_dir / "tests/outputs"
        
    def get_stage_configs(self) -> List[Path]:
        """Get all numbered configuration files in order."""
        return sorted(self.config_dir.glob("[0-9][0-9]_*.yaml"))
    
    def run_stage(self, config_path: Path) -> bool:
        """Run a single test stage using promptfoo."""
        print(f"\n=== Running stage: {config_path.stem} ===")
        
        # Create output path for this stage
        output_path = self.outputs_dir / f"{config_path.stem}_results.html"
        
        result = subprocess.run(
            ["promptfoo", "eval", 
             "-c", str(config_path),
             "--output", str(output_path)],
            capture_output=True,
            text=True
        )
        
        # Print the output regardless of success/failure
        if result.stdout:
            print(result.stdout)
        if result.returncode != 0:
            print(f"Error: {result.stderr}")
            
        return result.returncode == 0
    
    def run_all_stages(self) -> None:
        """Run all test stages in order."""
        for config in self.get_stage_configs():
            if not self.run_stage(config):
                print(f"\nStage {config.stem} failed. Stopping pipeline.")
                break
    
    def run_up_to_stage(self, target_stage: int) -> None:
        """Run all stages up to and including the target stage number."""
        for config in self.get_stage_configs():
            stage_num = int(config.stem.split("_")[0])
            if stage_num > target_stage:
                break
            if not self.run_stage(config):
                print(f"\nStage {config.stem} failed. Stopping pipeline.")
                break

def main():
    parser = argparse.ArgumentParser(description="Run prompt tests in stages")
    parser.add_argument("--up-to", type=int, help="Run all stages up to this number")
    parser.add_argument("--list", action="store_true", help="List all available test stages")
    
    args = parser.parse_args()
    runner = PromptTestRunner()
    
    if args.list:
        print("Available test stages:")
        for config in runner.get_stage_configs():
            print(f"  - {config.stem}")
    elif args.up_to is not None:
        runner.run_up_to_stage(args.up_to)
    else:
        runner.run_all_stages()

if __name__ == "__main__":
    main()