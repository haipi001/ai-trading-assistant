from pathlib import Path


class PromptTemplateLoader:
    def __init__(self, prompt_dir: Path | None = None):
        self.prompt_dir = prompt_dir or Path(__file__).resolve().parents[2] / "prompts"

    def load(self, template_name: str) -> str:
        safe_name = template_name.removesuffix(".md")
        if "/" in safe_name or "\\" in safe_name or ".." in safe_name:
            raise ValueError("prompt template name must be a simple file stem")

        prompt_path = self.prompt_dir / f"{safe_name}.md"
        if not prompt_path.exists():
            raise FileNotFoundError(f"prompt template not found: {safe_name}")

        return prompt_path.read_text(encoding="utf-8")
