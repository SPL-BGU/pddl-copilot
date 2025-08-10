import gradio as gr

from lllm_with_tools import ollama_request

# ---------------------------- #
# global variables
# ---------------------------- #
custom_css = """
#mytextbox textarea {
    color: blue;
    background-color: #f0f0f0;
    font-weight: bold;
}
#title {
    text-align: center;
}
"""


# ---------------------------- #
# GRADIO functions
# ---------------------------- #
def start(prompt, input_files=None):

    prompt = (
        "You are a helpful assistant that need to help the user with his PDDL planning problem.\n User: "
        + prompt
        + "\n"
    )
    if input_files:
        for file in input_files:
            prompt += f"The path to the file is: {file.name}\n"
        prompt += "Here is the content of these files:\n"
        for file in input_files:
            with open(file, "r") as file:
                content = file.read()
            prompt += f"```{content}```\n"
        last_msg, tools_used, tools_output = ollama_request(prompt=prompt)
    else:
        last_msg, tools_used, tools_output = ollama_request(
            prompt=prompt, chat_focus=True
        )

    return last_msg


# ---------------------------- #
# main blocks
# ---------------------------- #
with gr.Blocks(css=custom_css) as demo:
    gr.Markdown("# PDDL Planning Copilot", elem_id="title")
    with gr.Row():
        with gr.Column(scale=10):
            gr.Markdown("## Input Data")
            prompt = gr.Textbox(label="Describe the task")
            input_files = gr.File(
                label="Drop domain `.pddl` file", file_count="multiple"
            )
            run_llm = gr.Button("Run", variant="primary")

        with gr.Column(scale=12):
            gr.Markdown("## Output Result")
            output_expl = gr.Textbox(label="Explanation:", interactive=False)

        run_llm.click(
            fn=start,
            inputs=[prompt, input_files],
            outputs=[
                output_expl,
            ],
        )


# ---------------------------- #
# launch
# ---------------------------- #
demo.launch()
