"""
LangChain v0.1 code with ALL deprecated patterns.
Tests every auto-fix rule for the langchain package.
"""

# ── Original import path changes (already tested) ──
from langchain.schema import HumanMessage, AIMessage, SystemMessage
from langchain.chat_models import ChatOpenAI
from langchain.embeddings import OpenAIEmbeddings
from langchain.llms import OpenAI as OpenAILLM

# ── New import path changes ──
from langchain.schema.document import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter, CharacterTextSplitter
from langchain.vectorstores import Chroma, FAISS
from langchain.document_loaders import UnstructuredMarkdownLoader, TextLoader

# ── Community → provider (OpenAI only) ──
from langchain_community.chat_models import ChatOpenAI as CommunityChatOpenAI
from langchain_community.embeddings import OpenAIEmbeddings as CommunityOpenAIEmbeddings
from langchain_community.llms import OpenAI as CommunityOpenAILLM

# ── Function calling utilities ──
from langchain.utils.function_calling import convert_pydantic_to_openai_function, format_tool_to_openai_tool

result1 = convert_pydantic_to_openai_function(my_model)
result2 = convert_pydantic_to_openai_tool(my_model)
result3 = format_tool_to_openai_function(my_tool)
result4 = format_tool_to_openai_tool(my_tool)
result5 = convert_python_function_to_openai_function(my_func)

# ── Retriever methods ──
docs = retriever.get_relevant_documents(query)
async_docs = await retriever.aget_relevant_documents(query)

# ── ChatOpenAI without model ──
llm = ChatOpenAI()

# ── False positive guards (should NOT be rewritten) ──
from langchain_community.chat_models import ChatAnthropic
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.llms import Anthropic
ChatOpenAI(model="gpt-4", temperature=0.7)
ChatOpenAI(temperature=0.5)
