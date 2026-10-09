import json

transcript_path = "/Users/itaielron/.gemini/antigravity/brain/642e9b65-12bb-4d78-8943-7b33bc18a193/.system_generated/logs/transcript_full.jsonl"
output_path = "/Users/itaielron/Documents/antigravity/blissful-carson/chat_export.md"

with open(transcript_path, 'r') as f, open(output_path, 'w') as out:
    out.write("# Blissful Carson - Chat Export\n\n")
    for line in f:
        try:
            step = json.loads(line)
            source = step.get('source')
            type_ = step.get('type')
            content = step.get('content')
            
            if source == 'USER_EXPLICIT' and type_ == 'USER_INPUT':
                out.write(f"## USER:\n{content}\n\n---\n\n")
            elif source == 'MODEL' and type_ == 'PLANNER_RESPONSE':
                # Remove tool call blocks from content if necessary, or just dump raw
                out.write(f"## ASSISTANT:\n{content}\n\n---\n\n")
        except Exception as e:
            continue
            
print(f"Exported to {output_path}")
