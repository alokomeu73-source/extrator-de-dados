# app.py (VERSÃO REESTRUTURADA - Foco em Copiar Dados)

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
    page_title="Extrator de Guias (Copiar Texto)",
    page_icon="📋",
    layout="wide"
)

# Verifica a instalação do Tesseract
try:
    pytesseract.get_tesseract_version()
except pytesseract.TesseractNotFoundError:
    st.error(
        "Tesseract OCR não foi encontrado. "
        "Certifique-se de que o Tesseract está instalado e acessível no PATH do sistema."
    )
    st.stop()

# ==============================================================================
# 2️⃣ FUNÇÕES DE EXTRAÇÃO E OCR (Baseado na V4)
# ==============================================================================

def preprocess_image(image):
    """Aplica um pré-processamento para otimizar o OCR."""
    img = image.convert('L')
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(2.5)
    img = img.filter(ImageFilter.SHARPEN)
    return img

def extract_text_from_image(file_object):
    """Extrai texto de uma imagem usando Tesseract."""
    try:
        image = Image.open(file_object)
        processed_image = preprocess_image(image)
        # O layout automático (PSM 3) costuma ser um bom ponto de partida
        custom_config = r'--psm 3'
        text = pytesseract.image_to_string(processed_image, lang='por', config=custom_config)
        return text
    except Exception as e:
        st.error(f"Erro ao processar a imagem: {e}")
        return ""

def extract_text_from_pdf(pdf_file):
    """Extrai texto de PDF, aplicando OCR em páginas sem texto nativo."""
    try:
        pdf_file.seek(0)
        doc = fitz.open(stream=pdf_file.read(), filetype="pdf")
        full_text = ""
        
        # Se o PDF não tem texto extraível, assume-se que é escaneado
        if not any(page.get_text().strip() for page in doc):
            st.write(f"Arquivo PDF parece escaneado. Aplicando OCR...")
            for page in doc:
                pix = page.get_pixmap(dpi=300)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                full_text += extract_text_from_image(io.BytesIO(pix.tobytes("png"))) + "\n\n"
        else:
            for page in doc:
                full_text += page.get_text() + "\n\n"

        doc.close()
        return full_text
    except Exception as e:
        st.error(f"Erro ao processar o PDF: {e}")
        return ""


# ==============================================================================
# 3️⃣ FUNÇÃO DE EXTRAÇÃO DE DADOS (REGEX OTIMIZADO)
# ==============================================================================
def extract_medical_data(text):
    """Usa Regex para extrair os campos principais da Guia SP/SADT."""
    data = {
        "Número GUIA": "Não encontrado",
        "Registro ANS": "Não encontrado",
        "Data de Autorização": "Não encontrado",
        "Nome": "Não encontrado",
    }

    cleaned_text = re.sub(r'[\n\r]+', ' ', text)
    cleaned_text = re.sub(r'\s{2,}', ' ', cleaned_text)

    patterns = {
        "Registro ANS": r'(?:Registro\s*ANS|ANS)\s*.*?(\d{6})\b',
        "Número GUIA": r'Guia\s*Principal\s*[:\s]*(\d+)\b',
        "Data de Autorização": r'Data\s*de\s*Autoriza[çc][ãa]o\s*.*?(\d{2}/\d{2}/\d{4})',
        "Nome": r'10\s*-\s*Nome\s*([A-ZÀ-Ú\s]+?)\s*(?=\d{1,2}\s*-)'
    }

    for key, regex in patterns.items():
        match = re.search(regex, cleaned_text, re.IGNORECASE)
        if match:
            data[key] = match.group(1).strip()

    return data

# ==============================================================================
# 4️⃣ NOVA FUNÇÃO PARA FORMATAR SAÍDA DE TEXTO
# ==============================================================================

def format_data_for_copying(df):
    """Formata o DataFrame em uma string de texto para fácil cópia."""
    output_lines = []
    output_lines.append(f"## RESUMO DE {len(df)} GUIAS PROCESSADAS ##")
    output_lines.append("-" * 40)
    
    for _, row in df.iterrows():
        output_lines.append(f"Arquivo: {row['Arquivo']}")
        output_lines.append(f"Nome do Beneficiário: {row['Nome']}")
        output_lines.append(f"Número da Guia: {row['Número GUIA']}")
        output_lines.append(f"Registro ANS: {row['Registro ANS']}")
        output_lines.append(f"Data de Autorização: {row['Data de Autorização']}")
        output_lines.append("-" * 20)
        
    return "\n".join(output_lines)

# ==============================================================================
# 5️⃣ INTERFACE PRINCIPAL DO STREAMLIT
# ==============================================================================

st.title("📋 Extrator de Guias para Copiar Texto")
st.markdown("Faça o upload de guias (PDF ou imagem) e o sistema extrairá os dados em um formato de texto simples para você copiar.")

with st.sidebar:
    st.header("📤 Upload de Arquivos")
    uploaded_files = st.file_uploader(
        "Selecione as guias (PDF, PNG, JPG)",
        type=["pdf", "png", "jpg", "jpeg"],
        accept_multiple_files=True
    )
    st.divider()
    st.header("📖 Como Usar")
    st.markdown(
        """
        1. **Faça o upload** de um ou mais arquivos.
        2. **Aguarde** o processamento.
        3. **Copie o texto** gerado na área de resultados.
        """
    )

if uploaded_files:
    all_data = []
    progress_bar = st.progress(0, text="Iniciando...")

    for i, uploaded_file in enumerate(uploaded_files):
        file_name = uploaded_file.name
        progress_bar.progress((i + 1) / len(uploaded_files), text=f"Processando: {file_name}")

        try:
            file_io = io.BytesIO(uploaded_file.read())
            file_extension = os.path.splitext(file_name)[1].lower()
            text = ""

            if file_extension == ".pdf":
                text = extract_text_from_pdf(file_io)
            elif file_extension in [".png", ".jpg", ".jpeg"]:
                text = extract_text_from_image(file_io)

            extracted_data = extract_medical_data(text)
            extracted_data["Arquivo"] = file_name
            all_data.append(extracted_data)

        except Exception as e:
            st.error(f"Erro crítico ao processar '{file_name}': {e}")

    progress_bar.empty()

    if all_data:
        df = pd.DataFrame(all_data)[["Arquivo", "Nome", "Número GUIA", "Registro ANS", "Data de Autorização"]]
        
        st.header("✅ Dados Extraídos")
        st.markdown("Abaixo está o texto consolidado. Use o ícone no canto superior direito da caixa para copiar tudo.")
        
        formatted_text = format_data_for_copying(df)
        st.text_area("Resultado para cópia:", formatted_text, height=400)

else:
    st.info("Aguardando o upload de arquivos para iniciar o processamento.")
