import gradio as gr
import ast

from lllm_with_tools import call_ollama

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
def solve(input_domain, input_problem):
    with open(input_domain, "r") as file:
        domain_content = file.read()
    with open(input_problem, "r") as file:
        problem_content = file.read()
    chosen_algorithm, tool_result, explanation = call_ollama(
        f"""What tool should I use to solve the following planning problem?
        the path to the domain is: {input_domain}
        the path to the problem is: {input_problem}
        Here is the content of the domain and problem files:
        {domain_content} {problem_content}"""
    )

    tool_result = ast.literal_eval(tool_result)
    solution = tool_result[0]
    runtime = tool_result[1]
    sol_len = len(solution)

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
    # ARRANGEMENTS
    gr.Markdown("# LLM Heuristic Search Agent", elem_id="title")
    with gr.Row():
        with gr.Column(scale=10):
            gr.Markdown("## Input Data")
            input_domain = gr.File(label="Drop domain `.pddl` file")
            input_problem = gr.File(label="Drop problem `.pddl` file")
            solve_btn = gr.Button("Solve", variant="primary")
            # gr.Markdown("Example inputs:")
            # ex1_btn = gr.Button("Example 1")
            # ex2_btn = gr.Button("Example 2")
            # ex3_btn = gr.Button("Example 3")
        with gr.Column(scale=12):
            gr.Markdown("## Output Result")
            output_alg = gr.Textbox(label="Chosen algorithm:", interactive=False)
            output_expl = gr.Textbox(label="Explanation:", interactive=False)
            output_sol = gr.Textbox(label="Solution:", interactive=False)
            with gr.Row():
                output_sol_len = gr.Number(label="Solution Length:", interactive=False)
                output_rt = gr.Number(label="Runtime:", interactive=False)
            # output_env = gr.Video(
            #     label="Solution illustration:", autoplay=True, interactive=False
            # )
        solve_btn.click(
            fn=solve,
            inputs=[input_domain, input_problem],
            outputs=[
                output_alg,
                output_expl,
                output_sol,
                output_sol_len,
                output_rt,
                # output_env,
            ],
        )


# ---------------------------- #
# launch
# ---------------------------- #
demo.launch()
