import gradio as gr

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
    # Example values for the output
    print(input_domain, input_problem)
    chosen_algorithm, solution, explanation = call_ollama("Add 3 and 4")

    # chosen_algorithm = "A*"
    # explanation = "Found shortest path using A* algorithm."
    # solution = "Agent1: (1,1)->(2,2), Agent2: (3,3)->(4,4)"

    sol_len = 5
    runtime = 0.15
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
    gr.Markdown("# LLM Assistant for MAPF", elem_id="title")
    with gr.Row():
        with gr.Column(scale=10):
            gr.Markdown("## Input Data")
            input_domain = gr.File(label="Drop a `.pddl` file")
            input_problem = gr.File(label="Drop a `.pddl` file")
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
