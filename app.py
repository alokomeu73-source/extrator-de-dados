# app.py (VERSÃO OTIMIZADA)

# ==============================================================================
# 1️⃣ CONFIGURAÇÃO E IMPORTAÇÕES
# ==============================================================================
import streamlit as st
import pandas as pd
import fitz # PyMuPDF
import pytesseract
from PIL import Image, ImageEnhance, ImageFilter
import re
import io
import os
from datetime import datetime

st.set_page_config(
    page_title="Extrator de Guias (Otimizado)",
    page_icon="📋",
    layout="wide"
)

# Verifica a instalação do Tesseract.
try:
    pytesseract.get_tesseract_version()
except pytesseract.TesseractNotFoundError:
    st.error(
        "Tesseract OCR não foi encontrado. "
        "Certifique-se de que está instalado e acessível no PATH do sistema."
    )
    st.stop()

# ==============================================================================
# 2️⃣ FUNÇÕES DE EXTRAÇÃO E OCR
# ==============================================================================

def preprocess_image(image):
    """Aplica pré-processamento para otimizar o OCR."""
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
        # O psm 3 (layout automático) é geralmente a melhor opção para documentos
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
        
        has_native_text = any(page.get_text().strip() for page in doc)
        
        if not has_native_text:
            st.warning("Arquivo PDF parece escaneado. Aplicando OCR...")
            for page in doc:
                pix = page.get_pixmap(dpi=300)
                img_data = io.BytesIO(pix.tobytes("png"))
                full_text += extract_text_from_image(img_data) + "\n\n"
        else:
            for page in doc:
                full_text += page.get_text() + "\n\n"
        doc.close()
        return full_text
    except Exception as e:
        st.error(f"Erro ao processar o PDF: {e}")
        return ""

# ==============================================================================
# 3️⃣ FUNÇÃO DE EXTRAÇÃO DE DADOS (REGEX ROBUSTO)
# ==============================================================================
def extract_medical_data(text):
    """
    Usa Regex aprimorado para extrair os campos principais da Guia SP/SADT,
    levando em conta as variações do OCR.
    """
    data = {
        "Número GUIA": "Não encontrado",
        "Registro ANS": "Não encontrado",
        "Data de Autorização": "Não encontrado",
        "Nome": "Não encontrado",
    }

    # Limpeza e normalização do texto para facilitar o Regex
    cleaned_text = re.sub(r'[\n\r]+', ' ', text)
    cleaned_text = re.sub(r'\s{2,}', ' ', cleaned_text)
    
    # 🎯 Regex para os campos, ajustado para o layout da sua guia
    patterns = {
        # Número GUIA (Campo 2): Procura pelo rótulo "2 - Número GUIA"
        "Número GUIA": r'2\s*-\s*N[uú]mero\s*GUIA\s*.*?\s*(\d+)',
        
        # Nome do Beneficiário (Campo 10): Captura o texto entre o rótulo do nome e o próximo campo numerado (ex: 11)
        "Nome": r'10\s*-\s*Nome(?:\s*do\s*Benefici[áa]rio)?\s*([A-ZÀ-Ú\s]+?)(?=\s*\d{1,2}\s*-|\s*Data\s*do\s*Nascimento)',
        
        # Registro ANS: O Registro ANS do beneficiário (419010) está no campo 12.
        # Captura os primeiros 6 dígitos do número do cartão de saúde.
        "Registro ANS": r'12\s*-\s*N[uú]mero\s*do\s*Cart[ãa]o\s*Nacional\s*de\s*Sa[uú]de.*?\s*(\d{6})\d*',
        
        # Data de Autorização (Campo 4): Padrão confiável para a data
        "Data de Autorização": r'4\s*-\s*Data\s*de\s*Autoriza[çc][ãa]o\s*.*?(\d{2}/\d{2}/\d{4})',
    }

    for key, regex in patterns.items():
        match = re.search(regex, cleaned_text, re.IGNORECASE)
        if match:
            extracted_value = match.group(1).strip()
            # Tratamento especial para o nome
            if key == "Nome":
                # Capitaliza o nome
                data[key] = " ".join(word.capitalize() for word in extracted_value.split())
            else:
                data[key] = extracted_value

    return data

# ==============================================================================
# 4️⃣ FUNÇÃO PARA FORMATAR SAÍDA DE TEXTO
# ==============================================================================
def format_data_for_copying(df):
    """Formata o DataFrame em uma string de texto para fácil cópia."""
    output_lines = []
    output_lines.append(f"## RESUMO DE {len(df)} GUIAS PROCESSADAS ##")
    output_lines.append("-" * 45)
    
    for index, row in df.iterrows():
        output_lines.append(f"### GUIA {index + 1} ###")
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
st.markdown("Faça o upload de guias (PDF ou imagem) e o sistema extrairá os dados principais.")

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
            all_data.append({"Arquivo": file_name, "Nome": "ERRO", "Número GUIA": "ERRO", "Registro ANS": "ERRO", "Data de Autorização": "ERRO"})

    progress_bar.empty()

    if all_data:
        df = pd.DataFrame(all_data)[["Arquivo", "Nome", "Número GUIA", "Registro ANS", "Data de Autorização"]]
        
        st.header("✅ Dados Extraídos (Formato Tabela)")
        st.dataframe(df, use_container_width=True)
        
        st.header("📝 Resultado para Cópia")
        st.markdown("Use a caixa abaixo para copiar o texto consolidado.")
        
        formatted_text = format_data_for_copying(df)
        st.text_area("Resultado para cópia:", formatted_text, height=400)

    st.balloons()
else:
    st.info("Aguardando o upload de arquivos para iniciar o processamento. Faça o upload no painel lateral.")
