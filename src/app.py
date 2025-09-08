import sys
import platform

# Apply the ChromaDB fix only on Linux-based systems (like Streamlit Cloud)
if platform.system() == "Linux":
    __import__('pysqlite3')
    sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')

import streamlit as st
import json
import os
import pandas as pd
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_openai import ChatOpenAI
from langchain.chains import ConversationalRetrievalChain
from langchain.schema import Document
from langchain.retrievers.self_query.base import SelfQueryRetriever
from langchain.chains.query_constructor.base import AttributeInfo
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
    
    # Check if API keys are set
    if "OPENAI_API_KEY" not in os.environ:
        st.error("OpenAI API Key not found. Please set the OPENAI_API_KEY environment variable.")
        st.stop()

    # Combine data and create documents with rich metadata
    all_menu_items = starbucks_data + ediya_data + gongcha_data
    documents = []
    for item in all_menu_items:
        # Ensure all parts of the content are strings, defaulting to an empty string
        brand = item.get('brand') or ''
        name = item.get('name') or ''
        category = item.get('category') or ''
        description = item.get('description') or ''

        # Create the main content string
        content = f"""브랜드: {brand}
메뉴 이름: {name}
카테고리: {category}
설명: {description}
"""
        
        nutrition_str = ""
        if item.get('nutrition'):
            nutrition_str = "영양 정보:\n" + "\n".join([f"  {k}: {v}" for k, v in item['nutrition'].items()])

        # Ensure the final page_content is a non-empty string
        final_content = (content + "\n" + nutrition_str).strip()
        if not final_content or not name: # Skip items with no name and no content
            continue

        metadata = {
            "brand": brand,
            "name": name,
            "category": category,
        }
        
        # Parse all nutrition facts for metadata
        nutrition_info = item.get("nutrition")
        if nutrition_info:
            nutrition_keys = {
                "caffeine_mg": "카페인",
                "sugars_g": "당류",
                "sodium_mg": "나트륨",
                "protein_g": "단백질",
                "saturated_fat_g": "포화지방",
                "calories_kcal": "칼로리"
            }
            for meta_key, nutrition_key in nutrition_keys.items():
                value_str = nutrition_info.get(nutrition_key, "0")
                # Handle potential float values by splitting at '.' first
                numeric_part = "".join(filter(str.isdigit, value_str.split('.')[0]))
                metadata[meta_key] = int(numeric_part) if numeric_part else 0

        documents.append(Document(
            page_content=final_content,
            metadata=metadata
        ))

    # Initialize embeddings and vector store
    embeddings = OpenAIEmbeddings()
    persist_directory = "chroma_db_self_query"
    vectorstore = Chroma.from_documents(documents, embeddings, persist_directory=persist_directory)

    # Define metadata fields for the self-querying retriever
    metadata_field_info = [
        AttributeInfo(
            name="brand",
            description="음료의 브랜드. 사용자가 '스타벅스'를 언급하면 'Starbucks'를, '이디야'를 언급하면 'Ediya'를, '공차'를 언급하면 'Gong Cha'를 사용해야 합니다.",
            type="string",
        ),
        AttributeInfo(
            name="name",
            description="음료의 이름.",
            type="string",
        ),
        AttributeInfo(
            name="category",
            description="메뉴의 카테고리. 예를 들어, 공차의 카테고리는 '밀크티', '스무디', '커피'를 포함합니다.",
            type="string",
        ),
        AttributeInfo(
            name="caffeine_mg",
            description="음료의 카페인 함량 (밀리그램 단위).",
            type="integer",
        ),
        AttributeInfo(
            name="sugars_g",
            description="음료의 당류 함량 (g 단위).",
            type="integer",
        ),
        AttributeInfo(
            name="sodium_mg",
            description="음료의 나트륨 함량 (밀리그램 단위).",
            type="integer",
        ),
        AttributeInfo(
            name="protein_g",
            description="음료의 단백질 함량 (g 단위).",
            type="integer",
        ),
        AttributeInfo(
            name="saturated_fat_g",
            description="음료의 포화지방 함량 (g 단위).",
            type="integer",
        ),
        AttributeInfo(
            name="calories_kcal",
            description="음료의 칼로리 또는 열량 (kcal 단위).",
            type="integer",
        ),
    ]
    document_content_description = "커피 및 음료 메뉴에 대한 정보"

    # Initialize LLM and SelfQueryRetriever
    llm = ChatOpenAI(temperature=0, model_name="gpt-4o")
    retriever = SelfQueryRetriever.from_llm(
        llm,
        vectorstore,
        document_content_description,
        metadata_field_info,
        verbose=True
    )

    # Create the final chain
    qa_chain = ConversationalRetrievalChain.from_llm(llm, retriever)
    
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
            chat_history = []
            # Correctly pair user and assistant messages for history
            for i in range(0, len(st.session_state.messages[:-1]), 2):
                user_msg = st.session_state.messages[i]
                if i + 1 < len(st.session_state.messages[:-1]):
                    assistant_msg = st.session_state.messages[i+1]
                    if user_msg["role"] == "user" and assistant_msg["role"] == "assistant":
                        chat_history.append((user_msg["content"], assistant_msg["content"]))
            
            response = qa_chain.invoke({"question": st.session_state.messages[-1]["content"], "chat_history": chat_history})
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
