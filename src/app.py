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
    gongcha_path = os.path.join('data', 'gongcha_menu.json')
    
    starbucks_data = []
    ediya_data = []
    gongcha_data = []

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

    try:
        with open(gongcha_path, 'r', encoding='utf-8') as f:
            gongcha_data = json.load(f)
    except FileNotFoundError:
        st.error(f"Error: {gongcha_path} not found. Please run the gongcha_crawler.py first.")
        
    return starbucks_data, ediya_data, gongcha_data

# --- RAG Pipeline Setup ---
@st.cache_resource
def setup_rag_pipeline(starbucks_data, ediya_data, gongcha_data):
    """Sets up the RAG pipeline with combined menu data."""
    
    # Check if OpenAI API key is set
    if "OPENAI_API_KEY" not in os.environ:
        st.error("OpenAI API Key not found. Please set the OPENENAI_API_KEY environment variable.")
        st.stop() # Stop the app if API key is missing

    # Combine data and create documents
    all_menu_items = starbucks_data + ediya_data + gongcha_data
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
    llm = ChatOpenAI(temperature=0, model_name="gpt-3.5-turbo")
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
        # Set the active brand back to the brand of the item just viewed
        brand_mapping = {
            "Starbucks": "스타벅스",
            "Ediya": "이디야",
            "Gong Cha": "공차"
        }
        st.session_state['active_brand'] = brand_mapping.get(item.get('brand'), "스타벅스") # Default to Starbucks if brand not found
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

def get_categories(data):
    """Extracts unique categories from menu data."""
    categories = []
    for item in data:
        cat = item.get('category')
        if cat and cat not in categories:
            categories.append(cat)
    return categories

def kiosk_mode(starbucks_data, ediya_data, gongcha_data):
    """Renders the Kiosk UI."""
    if 'selected_item' in st.session_state:
        display_menu_item_details(st.session_state['selected_item'])
        return

    st.header("키오스크 모드")

    # Initialize session state
    if 'active_brand' not in st.session_state:
        st.session_state.active_brand = "스타벅스"
    if 'active_category' not in st.session_state:
        st.session_state.active_category = None

    brand_options = ["스타벅스", "이디야", "공차"]
    brand_data_map = {
        "스타벅스": starbucks_data,
        "이디야": ediya_data,
        "공차": gongcha_data
    }

    # Brand selection
    selected_brand = st.radio(
        "브랜드 선택",
        brand_options,
        index=brand_options.index(st.session_state.active_brand),
        horizontal=True,
        key='brand_selector'
    )

    # If brand changed, update state and rerun
    if selected_brand != st.session_state.active_brand:
        st.session_state.active_brand = selected_brand
        st.session_state.active_category = None # Reset category
        st.rerun()

    # Category selection
    current_data = brand_data_map[st.session_state.active_brand]
    categories = get_categories(current_data)

    if not categories:
        st.warning(f"{st.session_state.active_brand}에는 카테고리가 없습니다.")
        display_menu_grid(current_data, st.session_state.active_brand)
        return

    # Initialize category if it's not set or invalid
    if st.session_state.active_category is None or st.session_state.active_category not in categories:
        st.session_state.active_category = categories[0]

    selected_category = st.radio(
        "카테고리 선택",
        categories,
        index=categories.index(st.session_state.active_category),
        horizontal=True,
        key='category_selector'
    )

    # If category changed, update state and rerun
    if selected_category != st.session_state.active_category:
        st.session_state.active_category = selected_category
        st.rerun()

    # Filter and display
    filtered_menu = [item for item in current_data if item.get('category') == st.session_state.active_category]
    display_menu_grid(filtered_menu, st.session_state.active_brand)

# --- Chatbot Mode ---
@st.cache_data
def load_recommended_questions():
    """Loads recommended questions from a JSON file."""
    questions_path = os.path.join('data', 'recommended_questions.json')
    try:
        with open(questions_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        st.warning(f"Recommended questions file not found at {questions_path}. No recommendations will be displayed.")
        return []
    except json.JSONDecodeError:
        st.error(f"Error decoding JSON from {questions_path}. Please check the file format.")
        return []

def chatbot_mode(qa_chain):
    """Renders the Chatbot UI and handles interactions."""
    st.header("챗봇 모드")

    # Add a clear chat button
    if st.button("대화 초기화"): # You can place this button wherever you find it visually appropriate
        st.session_state.messages = []
        st.session_state.prompt_from_recommendation = None # Also clear any pending recommendation
        st.rerun()

    # Initialize chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    # Initialize prompt from recommendation
    if "prompt_from_recommendation" not in st.session_state:
        st.session_state.prompt_from_recommendation = None

    # Display chat messages from history on app rerun
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Display recommended questions if no chat history
    if not st.session_state.messages:
        recommended_questions = load_recommended_questions()
        if recommended_questions:
            st.subheader("추천 질문")
            cols = st.columns(3) # Adjust number of columns as needed
            for i, question in enumerate(recommended_questions):
                with cols[i % 3]: # Distribute questions across columns
                    if st.button(question, key=f"rec_q_{i}"):
                        st.session_state.prompt_from_recommendation = question
                        st.rerun()

    # React to user input or recommended question click
    prompt = st.chat_input("메뉴에 대해 궁금한 점을 물어보세요!")
    if st.session_state.prompt_from_recommendation:
        prompt = st.session_state.prompt_from_recommendation
        st.session_state.prompt_from_recommendation = None # Clear after use

    if prompt:
        # Add user message to chat history immediately
        st.session_state.messages.append({"role": "user", "content": prompt})
        # Force a rerun to update the UI (hide recommendations) before AI processing
        st.rerun()

    # Process AI response only if the last message was from the user and no AI response has been given yet
    if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
        with st.spinner("생각 중..."):
            # Get AI response
            # Prepare chat history for the chain
            chat_history = [(msg["content"], "") if msg["role"] == "user" else ("", msg["content"]) for msg in st.session_state.messages[:-1]]
            
            response = qa_chain({"question": st.session_state.messages[-1]["content"], "chat_history": chat_history})
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
    starbucks_data, ediya_data, gongcha_data = load_data()

    # Setup RAG pipeline (cached)
    qa_chain = setup_rag_pipeline(starbucks_data, ediya_data, gongcha_data)

    # Sidebar for mode selection
    mode = st.sidebar.radio("모드 선택", ("키오스크", "챗봇"))

    if mode == "키오스크":
        kiosk_mode(starbucks_data, ediya_data, gongcha_data)
    elif mode == "챗봇":
        chatbot_mode(qa_chain)

if __name__ == "__main__":
    main()
