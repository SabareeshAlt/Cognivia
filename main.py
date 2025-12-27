from langchain_ollama.llms import OllamaLLM
from langchain_core.prompts import ChatPromptTemplate
from vector import retriever

# Initialize the Ollama LLM model
model = OllamaLLM(model="llama2:latest")

# Updated prompt template to academic context
template = """
You are an expert academic assistant. Use the following context from academic papers to answer the user's question.
If you don't know the answer from the context, just say that you don't know. Don't try to make up an answer.

Context:
{reviews}

Question:
{question}
"""

# Create prompt and chain with model
prompt = ChatPromptTemplate.from_template(template)
chain = prompt | model

# Command line interface loop to interact with the RAG chain
while True:
    print("\n\n--------------")
    question = input("Ask your question (q to quit): ")
    print("\n\n")
    if question.lower() == "q":
        break

    # Retrieve relevant documents from vector store
    docs = retriever.invoke(question)

    # Format retrieved documents as context for prompt
    reviews = "\n".join([doc.page_content for doc in docs])

    # Get answer from chain
    result = chain.invoke({"reviews": reviews, "question": question})

    print("Answer:", result)

'''
#Tell me about the academic process to join the college. (Sample q to test)
from langchain_ollama.llms import OllamaLLM
from langchain_core.prompts import ChatPromptTemplate
from vector import retriever

model = OllamaLLM(model="llama2:latest")

template = """
You are an expert in answering questions about a pizza restaurant.
Here are some relevant reviews: {reviews}
Here is the question to answer: {question}
"""
prompt = ChatPromptTemplate.from_template(template)
chain = prompt | model

while True:
    print("\n\n--------------")
    question = input("Ask your question (q to quit): ")
    print("\n\n")
    if question.lower() == "q":
        break
    docs = retriever.invoke(question)
    reviews = "\n".join([doc.page_content for doc in docs])
    result = chain.invoke({"reviews": reviews, "question": question})
    print("Answer:", result)
'''

'''
#Old codes

from langchain_ollama.llms import OllamaLLM
from langchain_core.prompts import ChatPromptTemplate
from vector import retriever

# Initialize the Ollama LLM model
model = OllamaLLM(model="llama2:latest")

# Updated prompt template to academic context
template = """
You are an expert academic assistant. Use the following context from academic papers to answer the user's question.
If you don't know the answer from the context, just say that you don't know. Don't try to make up an answer.
Context:
{reviews}
Question:
{question}
"""

# Create prompt and chain with model
prompt = ChatPromptTemplate.from_template(template)
chain = prompt | model

# Command line interface loop to interact with the RAG chain
while True:
    print("\n\n--------------")
    question = input("Ask your question (q to quit): ")
    print("\n\n")
    if question.lower() == "q":
        break
    # Retrieve relevant documents from vector store
    docs = retriever.invoke(question)
    # Format retrieved documents as context for prompt
    reviews = "\n".join([doc.page_content for doc in docs])
    # Get answer from chain
    result = chain.invoke({"reviews": reviews, "question": question})
    print("Answer:", result)
'''