import json
import os

transcript_path = '/Users/itaielron/.gemini/antigravity/brain/c0df299c-545f-4292-b580-1c4542af62c7/.system_generated/logs/transcript.jsonl'
full_transcript_path = '/Users/itaielron/.gemini/antigravity/brain/c0df299c-545f-4292-b580-1c4542af62c7/.system_generated/logs/transcript_full.jsonl'
output_path = '/Users/itaielron/.gemini/antigravity/brain/c0df299c-545f-4292-b580-1c4542af62c7/conversation_export.md'

full_lines = {}
try:
    with open(full_transcript_path, 'r') as f:
        for line in f:
            obj = json.loads(line)
            full_lines[obj.get('step_index')] = obj
except Exception as e:
    print(f"Error reading full transcript: {e}")

with open(transcript_path, 'r') as f_in, open(output_path, 'w') as f_out:
    f_out.write("# Session Transcript Export\n\n")
    
    for line in f_in:
        try:
            obj = json.loads(line)
            step_idx = obj.get('step_index')
            source = obj.get('source')
            step_type = obj.get('type')
            
            content = obj.get('content', '')
            
            # If truncated, get from full transcript
            if 'truncated_fields' in obj and 'content' in obj['truncated_fields'] and step_idx in full_lines:
                content = full_lines[step_idx].get('content', content)
                
            if not content:
                continue
                
            if source == 'USER_EXPLICIT' and step_type == 'USER_INPUT':
                f_out.write(f"## USER\n{content}\n\n---\n\n")
            elif source == 'MODEL' and step_type == 'PLANNER_RESPONSE':
                # Remove tool calls from content if they are printed directly
                # Often the actual response text is what we want.
                f_out.write(f"## ASSISTANT\n{content}\n\n---\n\n")
        except Exception as e:
            pass

print(f"Exported to {output_path}")
