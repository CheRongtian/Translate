import streamlit as st
import requests
import PyPDF2
import docx
from PIL import Image
import pytesseract
import io

st.title("我的全能私有翻译官")

# 1. 增加一个文件上传组件
uploaded_file = st.file_uploader("直接拖拽文件到这里 (支持 TXT, PDF, Word, 图片)", type=['txt', 'pdf', 'docx', 'png', 'jpg', 'jpeg'])

# 2. 保留文本框，并且可以互相配合
user_input = st.text_area("或者直接粘贴文本：", height=150)

# 核心逻辑：提取文字
extracted_text = ""

if uploaded_file is not None:
    file_extension = uploaded_file.name.split('.')[-1].lower()
    
    try:
        if file_extension == 'txt':
            extracted_text = uploaded_file.read().decode('utf-8')
        
        elif file_extension == 'pdf':
            pdf_reader = PyPDF2.PdfReader(uploaded_file)
            for page in pdf_reader.pages:
                extracted_text += page.extract_text() + "\n"
                
        elif file_extension == 'docx':
            doc = docx.Document(uploaded_file)
            for para in doc.paragraphs:
                extracted_text += para.text + "\n"
                
        elif file_extension in ['png', 'jpg', 'jpeg']:
            image = Image.open(uploaded_file)
            # 使用 Tesseract 进行 OCR 识别，支持中英文
            extracted_text = pytesseract.image_to_string(image, lang='eng+chi_sim')
            
        st.success("文件文字提取成功！你可以直接点击翻译。")
        # 把提取出来的文字放进一个折叠框里让你预览，免得太长刷屏
        with st.expander("点击预览提取出的文字"):
            st.text(extracted_text)
            
    except Exception as e:
        st.error(f"解析文件出错了: {e}")

# 把上传文件提取的字和文本框手打的字合并起来
final_text_to_translate = extracted_text + "\n" + user_input

# 3. 翻译按钮
if st.button("开始翻译"):
    if final_text_to_translate.strip():
        st.info("正在呼叫后台 Qwen 进行翻译...")
        
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "qwen:7b",
                "prompt": f"请将以下文本翻译为中文，不要多余解释：\n{final_text_to_translate}",
                "stream": False
            }
        )
        
        result = response.json().get("response", "")
        st.success("翻译结果：")
        st.write(result)
    else:
        st.warning("你还没输入文本，也没上传带字的文件！")