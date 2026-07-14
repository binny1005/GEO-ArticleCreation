"""从 TestInput.md 提取 JSON 并保存到 data/kb.json"""
import json
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent

# Read TestInput.md
md_path = PROJECT / "GEO-种子问题生成工作流" / "TestInput.md"
with open(md_path, "r", encoding="utf-8") as f:
    content = f.read()

# Extract JSON from markdown code block
start = content.index("```json") + 7
end = content.rindex("```")
json_str = content[start:end].strip()

data = json.loads(json_str)

# Save
out_path = PROJECT / "data" / "kb.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"Saved: {out_path}")
print(f"Company: {data['input']['biz_params']['productBrand']}")
print(f"Sections: {[s['sectionCode'] for s in data['input']['biz_params']['sections']]}")
