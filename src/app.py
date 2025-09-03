import streamlit as st
import json
import os
import pandas as pd
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_openai import ChatOpenAI
from langchain.chains import ConversationalRetrievalChain
from langchain.schema import Document
# import openai # Not directly used for API key check anymore
from dotenv import load_dotenv

# --- Data Loading ---
@st.cache_data
def load_data():
    """Loads menu data from JSON files."""
    starbucks_path = os.path.join('data', 'starbucks_menu.json')
    ediya_path = os.path.join('data', 'ediya_menu.json')
    
    starbucks_data = []
    ediya_data = []

    try:
        with open(starbucks_path, 'r', encoding='utf-8') as f:
            starbucks_data = json.load(f)
    except FileNotFoundError:
        st.error(f"Error: {starbucks_path} not found. Please run the starbucks_crawler.py first.")
        
    try:
        with open(ediya_path, 'r', encoding='utf-8') as f:
            ediya_data = json.load(f)
    except FileNotFoundError:
        st.error(f"Error: {ediya_path} not found. Please run the ediya_crawler.py and ediya_deduplication.py first.")
        
    return starbucks_data, ediya_data

# --- RAG Pipeline Setup ---
@st.cache_resource
def setup_rag_pipeline(starbucks_data, ediya_data):
    """Sets up the RAG pipeline with combined menu data."""
    
    # Check if OpenAI API key is set
    if "OPENAI_API_KEY" not in os.environ:
        st.error("OpenAI API Key not found. Please set the OPENENAI_API_KEY environment variable.")
        st.stop() # Stop the app if API key is missing

    # Combine data and create documents
    all_menu_items = starbucks_data + ediya_data
    documents = []
    for item in all_menu_items:
        content = f"브랜드: {item.get('brand')}\n" \
                  f"메뉴 이름: {item.get('name')}\n" \
                  f"설명: {item.get('description')}\n"
        
        nutrition_str = ""
        if item.get('nutrition'):
            nutrition_str = "영양 정보:\n" + "\n".join([f"  {k}: {v}" for k, v in item['nutrition'].items()])
        
        documents.append(Document(page_content=content + nutrition_str, metadata={"source": item.get('brand'), "name": item.get('name')}))

    # Initialize embeddings and vector store
    embeddings = OpenAIEmbeddings()
    
    # Create a persistent ChromaDB instance
    persist_directory = "chroma_db"
    if not os.path.exists(persist_directory):
        os.makedirs(persist_directory)
        
    # Check if the collection already exists and has documents
    # This is a workaround as ChromaDB's from_documents doesn't have an overwrite option
    try:
        vectorstore = Chroma(persist_directory=persist_directory, embedding_function=embeddings)
        if vectorstore._collection.count() == 0: # If collection is empty, add documents
            print("Creating new ChromaDB collection...")
            vectorstore = Chroma.from_documents(documents, embeddings, persist_directory=persist_directory)
        else:
            print("Loading existing ChromaDB collection...")
    except Exception as e:
        print(f"Error loading/creating ChromaDB: {e}. Recreating...")
        vectorstore = Chroma.from_documents(documents, embeddings, persist_directory=persist_directory)


    # Initialize LLM and ConversationalRetrievalChain
    llm = ChatOpenAI(temperature=0, model_name="gpt-4o-mini")
    qa_chain = ConversationalRetrievalChain.from_llm(llm, vectorstore.as_retriever())
    
    return qa_chain

# --- Kiosk Mode ---
def display_menu_item_details(item):
    """Displays the details of a selected menu item."""
    st.header(item.get("name"))
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.image(item.get("image_url"), width='stretch')
    
    with col2:
        st.subheader("메뉴 설명")
        st.write(item.get("description", "설명이 없습니다."))
        
        st.subheader("영양 정보")
        nutrition_data = item.get("nutrition", {})
        if nutrition_data:
            df = pd.DataFrame(nutrition_data.items(), columns=['영양소', '함량'])
            st.dataframe(df, hide_index=True, width='stretch')
        else:
            st.write("영양 정보가 없습니다.")

    if st.button("<< 뒤로가기"):
        del st.session_state['selected_item']
        st.rerun()

def display_menu_grid(menu_data, brand_name):
    """Displays a grid of menu items."""
    if not menu_data:
        st.warning(f"{brand_name} 메뉴 데이터가 없습니다.")
        return

    st.subheader(f"{brand_name} 메뉴")
    
    # CSS to make the button full-width, with centered and wrapped text
    st.markdown("""
        <style>
            .stButton>button {
                width: 100%;
                white-space: normal; /* Allow text to wrap */
                word-break: break-word; /* Break long words if needed */
                text-align: center;
            }
        </style>
        """, unsafe_allow_html=True)

    columns = 4
    rows = len(menu_data) // columns + (1 if len(menu_data) % columns > 0 else 0)
    
    for i in range(rows):
        cols = st.columns(columns)
        for j in range(columns):
            index = i * columns + j
            if index < len(menu_data):
                item = menu_data[index]
                with cols[j]:
                    with st.container():
                        st.image(item.get("image_url"), width='stretch')
                        button_key = f"{brand_name}_{item.get('name')}_{index}" # Use index for uniqueness
                        if st.button(item.get("name"), key=button_key):
                            st.session_state['selected_item'] = item
                            st.rerun()

def kiosk_mode(starbucks_data, ediya_data):
    """Renders the Kiosk UI."""
    if 'selected_item' in st.session_state:
        display_menu_item_details(st.session_state['selected_item'])
    else:
        st.header("키오스크 모드")
        tab_starbucks, tab_ediya = st.tabs(["스타벅스 (Starbucks)", "이디야 (Ediya)"])
        with tab_starbucks:
            display_menu_grid(starbucks_data, "스타벅스")
        with tab_ediya:
            display_menu_grid(ediya_data, "이디야")

# --- Chatbot Mode ---
def chatbot_mode(qa_chain):
    """Renders the Chatbot UI and handles interactions."""
    st.header("챗봇 모드")

    # Initialize chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Display chat messages from history on app rerun
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # React to user input
    if prompt := st.chat_input("메뉴에 대해 궁금한 점을 물어보세요!"):
        # Display user message in chat message container
        st.chat_message("user").markdown(prompt)
        # Add user message to chat history
        st.session_state.messages.append({"role": "user", "content": prompt})

        with st.spinner("생각 중..."):
            # Get AI response
            # Prepare chat history for the chain
            chat_history = [(msg["content"], "") if msg["role"] == "user" else ("", msg["content"]) for msg in st.session_state.messages[:-1]]
            
            response = qa_chain({"question": prompt, "chat_history": chat_history})
            ai_response = response["answer"]

            # Display assistant response in chat message container
            with st.chat_message("assistant"):
                st.markdown(ai_response)
            # Add assistant response to chat history
            st.session_state.messages.append({"role": "assistant", "content": ai_response})

# --- Main App ---
def main():
    """Main function to run the Streamlit app."""
    st.set_page_config(layout="wide", page_title="커피 프랜차이즈 메뉴 정보 및 추천 시스템")
    st.title("커피 프랜차이즈 메뉴 정보 및 추천 시스템")

    load_dotenv()

    # Load data
    starbucks_data, ediya_data = load_data()

    # Setup RAG pipeline (cached)
    qa_chain = setup_rag_pipeline(starbucks_data, ediya_data)

    # Sidebar for mode selection
    mode = st.sidebar.radio("모드 선택", ("키오스크", "챗봇"))

    if mode == "키오스크":
        kiosk_mode(starbucks_data, ediya_data)
    elif mode == "챗봇":
        chatbot_mode(qa_chain)

if __name__ == "__main__":
    main()
