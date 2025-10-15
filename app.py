# app.py (VERSÃO FINAL OTIMIZADA PARA GUIAS SP/SADT)

# ==============================================================================
# 1️⃣ CONFIGURAÇÃO E IMPORTAÇÕES
# ==============================================================================
import streamlit as st
import pandas as pd
import fitz  # PyMuPDF
import pytesseract
from PIL import Image, ImageEnhance, ImageFilter
import re
import io
import os
from datetime import datetime

st.set_page_config(
    page_title="Extrator de Guias Médicas",
    page_icon="🩺",
    layout="wide"
)

# Verifica a instalação do Tesseract e exibe erro, mas não para o app
try:
    pytesseract.get_tesseract_version()
except pytesseract.TesseractNotFoundError:
    st.error(
        "Tesseract OCR não foi encontrado. "
        "Certifique-se de que o arquivo 'packages.txt' com 'tesseract-ocr' "
        "está no seu repositório do GitHub."
    )

# ==============================================================================
# 2️⃣ FUNÇÕES DE EXTRAÇÃO E OCR (Otimizadas para Guia)
# ==============================================================================

def preprocess_image(image):
    """
    Aplica um pré-processamento mais robusto para melhorar a qualidade do OCR.
    - Contraste mais alto e nitidez.
    """
    img = image.convert('L')
    
    # 1. Aumentar o contraste
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(3.0) 
    
    # 2. Aplicar nitidez
    img = img.filter(ImageFilter.SHARPEN)
    
    # 3. Binarização
    img = img.point(lambda x: 0 if x < 150 else 255, '1')
    
    return img

def extract_text_from_image(file_object):
    """Extrai texto de uma imagem usando Tesseract com configuração otimizada."""
    try:
        image = Image.open(file_object)
        processed_image = preprocess_image(image)
        # Configuração do Tesseract: PSM 3 (totalmente automático)
        custom_config = r'--psm 3'
        text = pytesseract.image_to_string(processed_image, lang='por', config=custom_config)
        return text
    except Exception as e:
        st.error(f"Erro ao processar a imagem: {e}") 
        return ""

def extract_text_from_pdf(pdf_file):
    """Extrai texto de PDF, com lógica de OCR aprimorada para páginas escaneadas."""
    try:
        pdf_file.seek(0)
        pdf_bytes = pdf_file.read()
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        full_text = ""
        has_readable_text = any(page.get_text().strip() for page in doc)

        if not has_readable_text:
            st.write(f"Arquivo parece ser totalmente escaneado. Ativando OCR em todas as páginas.")
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                pix = page.get_pixmap(dpi=300) 
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                processed_image = preprocess_image(img)
                
                custom_config = r'--psm 3' 
                full_text += pytesseract.image_to_string(processed_image, lang='por', config=custom_config) + "\n\n"
        else:
            for page in doc:
                full_text += page.get_text() + "\n\n"

        doc.close()
        return full_text
    except Exception as e:
        st.error(f"Erro ao processar o PDF: {e}")
        return ""


# ==============================================================================
# 3️⃣ FUNÇÃO DE EXTRAÇÃO DE DADOS (REGEX OTIMIZADO PARA GUIAS)
# ==============================================================================
def extract_medical_data(text):
    """Usa expressões regulares específicas e pré-limpeza para a Guia SP/SADT."""
    data = {
        "Número GUIA": "Não encontrado",
        "Registro ANS": "Não encontrado",
        "Data de Autorização
