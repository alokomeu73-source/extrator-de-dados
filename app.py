# app.py (VERSÃO CORRIGIDA)

# ==============================================================================
# 1️⃣ CONFIGURAÇÃO E IMPORTAÇÕES (Ajuste no tratamento de erro Tesseract)
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
# 2️⃣ FUNÇÕES DE EXTRAÇÃO E OCR (COM MELHORIAS E AJUSTE PARA IO.BytesIO)
# ==============================================================================

def preprocess_image(image):
    """
    Aplica um pré-processamento mais robusto para melhorar a qualidade do OCR.
    """
    img = image.convert('L')
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(2.0)
    # Binarização: converte pixels cinzas para preto ou branco
    img = img.point(lambda x: 0 if x < 180 else 255, '1')
    return img

def extract_text_from_image(file_object):
    """Extrai texto de uma imagem usando Tesseract com configuração otimizada."""
    try:
        # Image.open() pode receber o objeto io.BytesIO
        image = Image.open(file_object)
        processed_image = preprocess_image(image)
        # Configuração do Tesseract:
        custom_config = r'--psm 6'
        text = pytesseract.image_to_string(processed_image, lang='por', config=custom_config)
        return text
    except Exception as e:
        # 'file_object' pode ser io.BytesIO.name se você configurou, senão use str(e)
        st.error(f"Erro ao processar a imagem: {e}") 
        return ""

def extract_text_from_pdf(pdf_file):
    """Extrai texto de PDF, com lógica de OCR aprimorada para páginas escaneadas."""
    try:
        pdf_file.seek(0) # Volta ao início para leitura segura
        pdf_bytes = pdf_file.read()
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        full_text = ""
        has_readable_text = any(page.get_text().strip() for page in doc)

        # Se o PDF não tiver texto legível, trate-o como totalmente escaneado
        if not has_readable_text:
            # Não use st.info aqui dentro do st.status, use st.write
            st.write(f"Arquivo parece ser totalmente escaneado. Ativando OCR em todas as páginas.")
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                pix = page.get_pixmap(dpi=300)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                processed_image = preprocess_image(img)
                custom_config = r'--psm 6'
                full_text += pytesseract.image_to_string(processed_image, lang='por', config=custom_config) + "\n\n"
        else: # Extrai texto diretamente
            for page in doc:
                full_text += page.get_text() + "\n\n"

        doc.close()
        return full_text
    except Exception as e:
        st.error(f"Erro ao processar o PDF: {e}")
        return ""


# ==============================================================================
# 3️⃣ FUNÇÃO DE EXTRAÇÃO DE DADOS (REGEX REFINADO) - Sem alterações
# ==============================================================================
def extract_medical_data(text):
    """Usa expressões regulares mais flexíveis e robustas."""
    data = {
        "Número GUIA": "Não encontrado",
        "Registro ANS": "Não encontrado",
        "Data de Autorização": "Não encontrado",
        "Nome": "Não encontrado",
    }
    
    # --- Padrões de Regex Aprimorados ---
    patterns = {
        "Número GUIA": [
            r'(?:N[º°]?\s*da\s*Guia|N[úu]mero\s*da\s*Guia|Guia\s*N[º°]?|GUIA\s*PRINCIPAL)\s*:?\s*(\d{12,})',
            r'(\b\d{20}\b)' # Procura por um número de 20 dígitos solto no texto
        ],
        "Registro ANS": [
            r'(?:Registro\s*ANS)\s*:?\s*(\d{6}\b)'
        ],
        "Data de Autorização": [
            r'(?:Data\s*(?:da\s*)?Autoriza[çc][ãa]o)\s*:?\s*(\d{2}/\d{2}/\d{4})'
        ],
        "Nome": [
            # Captura o texto na mesma linha após o rótulo, permitindo letras minúsculas.
            r'(?:Nome\s*(?:do\s*Benefici[áa]rio)?|Benefici[áa]rio)\s*:?\s*([A-Za-zÀ-ú\s]{5,})'
        ]
    }

    # Itera sobre cada campo e tenta encontrar uma correspondência
    for key, regex_list in patterns.items():
        for regex in regex_list:
            match = re.search(regex, text, re.IGNORECASE)
            if match:
                # Limpa espaços extras e quebras de linha do resultado
                found_text = match.group(1).strip().replace('\n', ' ')
                data[key] = re.sub(r'\s{2,}', ' ', found_text)
                break # Pára no primeiro padrão que funcionar para este campo

    return data


# ==============================================================================
# 4️⃣ Geração de Excel e Interface (COM CORREÇÃO DO FLUXO DO ARQUIVO)
# ==============================================================================

def to_excel(df_to_export):
    """Converte um DataFrame para um arquivo Excel em memória com formatação."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_to_export.to_excel(writer, index=False, sheet_name='Guias_Medicas')
        workbook = writer.book
        worksheet = writer.sheets['Guias_Medicas']
        
        header_format = workbook.add_format({
            'bold': True, 'text_wrap': True, 'valign': 'top',
            'fg_color': '#2E8B57', 'font_color': 'white', 'border': 1
        })
        
        for col_num, value in enumerate(df_to_export.columns.values):
            worksheet.write(0, col_num, value, header_format)
        
        for idx, col in enumerate(df_to_export):
            series = df_to_export[col]
            max_len = max((series.astype(str).map(len).max(), len(str(series.name)))) + 2
            worksheet.set_column(idx, idx, max_len)
            
    return output.getvalue()

st.title("🩺 Extrator de Informações de Guias Médicas")
st.markdown("Faça o upload de guias em formato PDF ou imagem. O sistema usará OCR para extrair os dados e apresentá-los em uma tabela editável.")

with st.sidebar:
    st.header("📤 Upload de Arquivos")
    uploaded_files = st.file_uploader(
        "Selecione as guias (PDF, PNG, JPG)",
        type=["pdf", "png", "jpg", "jpeg"],
        accept_multiple_files=True
    )
    st.header("🛠️ Opções")
    show_debug_text = st.checkbox("Mostrar texto extraído (debug)")
    
    st.divider()
    
    st.header("📖 Como Usar")
    st.markdown(
        """
        1. **Faça o upload** de um ou mais arquivos de guias médicas.
        2. **Aguarde o processamento**. O progresso será exibido na tela.
        3. **Revise e edite** os dados na tabela interativa que aparecerá.
        4. **Baixe os resultados** em formato Excel (.xlsx) ou CSV.
        """
    )

if 'processed_data' not in st.session_state:
    st.session_state.processed_data = pd.DataFrame()

if uploaded_files:
    all_data = []
    progress_bar = st.progress(0, text="Iniciando...")

    for i, uploaded_file in enumerate(uploaded_files):
        file_name = uploaded_file.name
        progress_bar.progress((i + 1) / len(uploaded_files), text=f"Processando: {file_name}")

        try:
            # *** CORREÇÃO: CRIAÇÃO DE UM OBJETO IO.BytesIO SEGURO ***
            # Garante que o ponteiro do arquivo esteja no início e cria uma cópia em memória
            uploaded_file.seek(0)
            file_io = io.BytesIO(uploaded_file.read())
            file_io.name = file_name # Mantém o nome para fins de log
            
            with st.status(f"Analisando '{file_name}'...", expanded=False) as status:
                file_extension = os.path.splitext(file_name)[1].lower()
                text = ""
                
                if file_extension == ".pdf":
                    st.write("Lendo arquivo PDF...")
                    # Passa o objeto io.BytesIO, não o uploaded_file original
                    text = extract_text_from_pdf(file_io) 
                elif file_extension in [".png", ".jpg", ".jpeg"]:
                    st.write("Lendo arquivo de imagem...")
                    # Passa o objeto io.BytesIO, não o uploaded_file original
                    text = extract_text_from_image(file_io) 
                
                st.write("Extraindo dados do texto...")
                extracted_data = extract_medical_data(text)
                
                # ATUALIZAÇÃO DO STATUS: Esta é a parte que falhava
                if all(v == "Não encontrado" for v in extracted_data.values()):
                    status.update(label=f"Nenhum dado encontrado em '{file_name}'", state="warning", expanded=False)
                else:
                    status.update(label=f"Extração concluída para '{file_name}'!", state="complete", expanded=False)

                extracted_data["Arquivo"] = file_name
                all_data.append(extracted_data)

                if show_debug_text:
                    st.expander(f"📝 Texto bruto extraído de '{file_name}'").text_area("", text, height=250)
        
        except Exception as e:
            # Trata qualquer exceção que possa ter encerrado o contexto
            st.error(f"Erro crítico ao processar '{file_name}'. Tente novamente ou use outro arquivo. Detalhe: {e}")
            
    
    progress_bar.empty()

    if all_data:
        # Garante que o DataFrame seja sempre criado, mesmo que com erros parciais
        df = pd.DataFrame(all_data)[["Arquivo", "Número GUIA", "Registro ANS", "Data de Autorização", "Nome"]]
        st.session_state.processed_data = df

if not st.session_state.processed_data.empty:
    st.header("📋 Resultados Editáveis")
    
    edited_df = st.data_editor(
        st.session_state.processed_data,
        num_rows="dynamic",
        use_container_width=True,
        key="data_editor"
    )

    st.header("⬇️ Download")
    col1, col2, _ = st.columns([1, 1, 3])

    with col1:
        excel_data = to_excel(edited_df)
        timestamp = datetime.now().strftime("%Y%m%d")
        st.download_button(
            label="📥 Baixar Excel",
            data=excel_data,
            file_name=f"guias_medicas_{timestamp}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
    with col2:
        csv_data = edited_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📄 Baixar CSV",
            data=csv_data,
            file_name=f"guias_medicas_{timestamp}.csv",
            mime="text/csv",
            use_container_width=True
        )
else:
    st.info("Aguardando o upload de arquivos para iniciar o processamento.")
