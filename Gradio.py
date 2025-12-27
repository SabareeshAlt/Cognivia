import gradio as gr
from langchain_ollama.llms import OllamaLLM
from langchain_core.prompts import ChatPromptTemplate
from vector import retriever

model = OllamaLLM(model="llama2:latest")
template = """
You are an expert in answering questions about the college.
Here are some relevant reviews: {reviews}
Here is the question to answer: {question}
"""
prompt = ChatPromptTemplate.from_template(template)
chain = prompt | model

def answer_question(history, user_message):
    history = history or []
    history.append({"role": "user", "content": user_message})
    docs = retriever.invoke(user_message)
    reviews = "\n".join([doc.page_content for doc in docs])
    answer = chain.invoke({"reviews": reviews, "question": user_message})
    history.append({"role": "assistant", "content": answer})
    return history, gr.update(value=""), gr.update(visible=True), ""

def show_input(history):
    return gr.update(visible=True), gr.update(visible=False)

def clear_chat():
    return [], gr.update(visible=True), gr.update(visible=False), ""

with gr.Blocks(
    theme=gr.themes.Base(),
    css="""
body { background: #18191A; }
/* Increase chatbot height and max-width */
#chatbot {
    height: 600px !important;
    max-width: 1200px !important;
    margin: 40px auto 0 auto !important;
    min-height: 350px !important;
    overflow-y: auto;
    border-radius: 12px !important;
    box-shadow: 0 4px 24px #0007;
    background: #222 !important;
}
.gradio-container {
    padding-bottom: 50px !important;
}
/* Chat output text size */
#chatbot .chatbot-message p,
#chatbot .chatbot-message li,
#chatbot .chatbot-message,
.gr-box *, .gradio-container * {
    font-size: 26px !important;
    line-height: 1.5 !important;
    color: #eee !important;
}
/* Input box styling */
#input_box textarea {
    font-size: 30px !important;
    line-height: 1.3 !important;
    width: 100% !important;
    min-width: 0 !important;
}
/* Container for input and buttons */
#input_container {
    max-width: 650px !important;
    margin: 0 auto !important;
}
/* Button row styling */
#button_row {
    width: 100% !important;
    display: flex;
    gap: 10px;
    justify-content: space-between;
    margin-top: 8px;
}
/* Buttons styling */
.gr-button {
    flex: 1 1 0;
    min-width: 150px !important;
    font-size: 18px !important;
    padding: 10px 20px !important;
    border-radius: 8px !important;
}
/* Space below buttons */
.gr-row {
    margin-bottom: 50px !important;
}
"""
) as demo:
    gr.Markdown("<h1 style='text-align:center; color:#FF5722;'>AcademeRAG</h1>")
    gr.Markdown("<p style='text-align:center; font-size:18px; color:#bbb;'>Ask a question.</p>")
    chatbot = gr.Chatbot(label="Chat", elem_id="chatbot", type="messages")
    state = gr.State([])

    with gr.Column(elem_id="input_container"):
        input_box = gr.Textbox(
            placeholder="Type your question here and press Enter",
            show_label=False,
            elem_id="input_box"
        )
        with gr.Row(elem_id="button_row"):
            ask_another_btn = gr.Button("Ask another question", visible=False)
    input_box.submit(answer_question, inputs=[state, input_box],
                     outputs=[chatbot, input_box, ask_another_btn, input_box])
    ask_another_btn.click(show_input, inputs=[state], outputs=[input_box, ask_another_btn])
demo.launch()
