with open("kanban_app.py", "r") as f:
    code = f.read()

# Replace st.image(filepath) with st.image(bytes)
old_line = 'st.image(os.path.join(chart_dir, chart), caption=chart, use_container_width=True)'
new_line = '''with open(os.path.join(chart_dir, chart), "rb") as img_file:
                    img_bytes = img_file.read()
                st.image(img_bytes, caption=chart, use_container_width=True)'''

code = code.replace(old_line, new_line)

with open("kanban_app.py", "w") as f:
    f.write(code)
