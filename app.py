import gradio as gr
import ast

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
def start(prompt, input_domain=None, input_problem=None, input_plan=None):

    prompt = (
        "You are a helpful assistant that need to help the user with his PDDL planning problem.\n User: "
        + prompt
        + "\n"
    )

    if input_domain:
        prompt += f"The path to the domain is: {input_domain}\n"
        with open(input_domain, "r") as file:
            domain_content = file.read()
    else:
        domain_content = None

    if input_problem:
        prompt += f"The path to the problem is: {input_problem}\n"
        with open(input_problem, "r") as file:
            problem_content = file.read()
    else:
        problem_content = None

    if input_plan:
        prompt += f"The path to the plan is: {input_plan}\n"
        with open(input_plan, "r") as file:
            plan_content = file.read()
    else:
        plan_content = None

    if domain_content or problem_content or plan_content:
        prompt += "Here is the content of these files:\n"

        for content in [domain_content, problem_content, plan_content]:
            if content is None:
                continue

            prompt += f"```{content}```\n"

        chosen_algorithm, tool_result, explanation = ollama_request(prompt=prompt)
    else:
        chosen_algorithm, tool_result, explanation = ollama_request(
            prompt=prompt, chat_focus=True
        )

    try:
        tool_result = ast.literal_eval(tool_result)
        if len(tool_result) == 2:
            solution = tool_result[0]
            runtime = tool_result[1]
        else:
            solution = tool_result
            runtime = None
        sol_len = len(solution)
    except:
        solution = tool_result
        runtime = None
        sol_len = None

    # solution_video_path = (
    #     "path_to_video.mp4"  # must be a path or URL accessible by Gradio
    # )

    return (
        chosen_algorithm,
        explanation,
        solution,
        sol_len,
        runtime,
        # solution_video_path,
    )


# ---------------------------- #
# main blocks
# ---------------------------- #
with gr.Blocks(css=custom_css) as demo:
    gr.Markdown("# PDDL Planning Copilot", elem_id="title")
    with gr.Row():
        with gr.Column(scale=10):
            gr.Markdown("## Input Data")
            prompt = gr.Textbox(label="Describe the task")
            input_domain = gr.File(label="Drop domain `.pddl` file")
            input_problem = gr.File(label="Drop problem `.pddl` file")
            input_plan = gr.File(label="Drop plan `.solution` file")
            run_llm = gr.Button("Run", variant="primary")

        with gr.Column(scale=12):
            gr.Markdown("## Output Result")
            output_alg = gr.Textbox(label="Chosen algorithm:", interactive=False)
            output_expl = gr.Textbox(label="Explanation:", interactive=False)
            output_sol = gr.Textbox(label="Solution:", interactive=False)
            with gr.Row():
                output_sol_len = gr.Number(label="Solution Length:", interactive=False)
                output_rt = gr.Number(label="Runtime:", interactive=False)

        run_llm.click(
            fn=start,
            inputs=[prompt, input_domain, input_problem, input_plan],
            outputs=[
                output_alg,
                output_expl,
                output_sol,
                output_sol_len,
                output_rt,
            ],
        )


# ---------------------------- #
# launch
# ---------------------------- #
demo.launch()
