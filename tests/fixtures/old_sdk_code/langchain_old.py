"""Old-style LangChain code (v0.1.x). Used for auto-fix tests."""

from langchain.schema import HumanMessage, AIMessage, SystemMessage
from langchain.chat_models import ChatOpenAI
from langchain.embeddings import OpenAIEmbeddings
from langchain.llms import OpenAI

# Old-style model usage
llm = ChatOpenAI(model="gpt-4")
messages = [HumanMessage(content="Hello!")]
response = llm(messages)
