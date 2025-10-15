# app.py

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

# --- Configuração da Página Streamlit ---
st.set_page_config(
    page_title="Extrator de Guias Médicas",
    page_icon="🩺",
    layout="wide"
)

# AVISO IMPORTANTE: Em ambientes como o Streamlit Community Cloud, o Tesseract
# é instalado via packages.txt e já está no PATH do sistema, portanto,
# pytesseract o encontrará sem precisar de configuração manual do caminho.
try:
    pytesseract.get_tesseract_version()
except pytesseract.TesseractNotFoundError:
    st.error(
        "Tesseract OCR não foi encontrado. "
        "Certifique-se de que o arquivo 'packages.txt' com 'tesseract-ocr' "
        "está no seu repositório do GitHub."
    )
    st.stop()

# ==============================================================================
# 2️⃣ FUNÇÕES DE EXTRAÇÃO E OCR
# ==============================================================================

def preprocess_image(image):
    """Aplica pré-processamento a uma imagem para melhorar a qualidade do OCR."""
    img = image.convert('L')  # Converte para escala de cinza
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(2.0) # Aumenta o contraste
    img = img.filter(ImageFilter.SHARPEN) # Aplica filtro de nitidez
    return img

def extract_text_from_image(image_file):
    """Extrai texto de um arquivo de imagem usando Tesseract OCR."""
    try:
        image = Image.open(image_file)
        processed_image = preprocess_image(image)
        # Usa o idioma 'por' (português) instalado via packages.txt
        text = pytesseract.image_to_string(processed_image, lang='por')
        return text
    except Exception as e:
        st.error(f"Erro ao processar a imagem '{image_file.name}': {e}")
        return ""

def extract_text_from_pdf(pdf_file):
    """
    Extrai texto de um PDF. Se o PDF for baseado em imagem (escaneado),
    converte suas páginas em imagens e aplica OCR.
    """
    try:
        pdf_bytes = pdf_file.read()
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        full_text = ""
        is_scanned = False

        # Verifica se o PDF contém texto legível ou é escaneado
        for page_num, page in enumerate(doc):
            page_text = page.get_text().strip()
            if len(page_text) < 50: # Heurística: se a página tem pouco ou nenhum texto, pode ser escaneada
                is_scanned = True
                st.info(f"Arquivo '{pdf_file.name}' detectado como escaneado. Ativando OCR.")
                break # Sai do loop na primeira página escaneada
            full_text += page_text + "\n"

        if is_scanned:
            full_text = ""
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                # Renderiza a página em alta resolução para melhor OCR
                pix = page.get_pixmap(dpi=300)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                processed_image = preprocess_image(img)
                full_text += pytesseract.image_to_string(processed_image, lang='por') + "\n"

        doc.close()
        return full_text
    except Exception as e:
        st.error(f"Erro ao processar o PDF '{pdf_file.name}': {e}")
        return ""

# ==============================================================================
# 3️⃣ FUNÇÃO DE EXTRAÇÃO DE DADOS (REGEX)
# ==============================================================================
def extract_medical_data(text):
    """Usa expressões regulares (regex) para extrair os campos de interesse."""
    data = {
        "Número GUIA": "Não encontrado",
        "Registro ANS": "Não encontrado",
        "Data de Autorização": "Não encontrado",
        "Nome": "Não encontrado",
    }
    
    # Regex são "tentativas" de encontrar padrões; podem precisar de ajustes
    # para layouts de guias diferentes.
    patterns = {
        "Número GUIA": r'(?:N[º°]?\s*da\s*Guia|GUIA\s*PRINCIPAL|N[úu]mero\s*da\s*Guia)\s*:?\s*(\d{12,})',
        "Registro ANS": r'Registro\s*ANS\s*:?\s*(\d{6})',
        "Data de Autorização": r'Data\s*(?:da\s*)?Autoriza[çc][ãa]o\s*:?\s*(\d{2}/\d{2}/\d{4})',
        "Nome": r'(?:Nome\s*(?:do\s*Benefici[áa]rio)?|Benefici[áa]rio)\s*:?\s*([A-ZÀ-Ú\s]{5,})'
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            # Limpa espaços extras do resultado encontrado
            data[key] = re.sub(r'\s{2,}', ' ', match.group(1).strip())
            
    return data

# ==============================================================================
# 4️⃣ FUNÇÃO PARA GERAR PLANILHA EXCEL
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
        
        # Auto-ajuste da largura das colunas
        for idx, col in enumerate(df_to_export):
            series = df_to_export[col]
            max_len = max((series.astype(str).map(len).max(), len(str(series.name)))) + 2
            worksheet.set_column(idx, idx, max_len)
            
    return output.getvalue()

# ==============================================================================
# 5️⃣ INTERFACE PRINCIPAL DO STREAMLIT
# ==============================================================================

st.title("🩺 Extrator de Informações de Guias Médicas")
st.markdown("Faça o upload de guias em formato PDF ou imagem. O sistema usará OCR para extrair os dados e apresentá-los em uma tabela editável.")

# --- Barra Lateral (Sidebar) ---
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

# --- Lógica de Processamento e Exibição ---
if 'processed_data' not in st.session_state:
    st.session_state.processed_data = pd.DataFrame()

if uploaded_files:
    all_data = []
    progress_bar = st.progress(0, text="Iniciando...")

    for i, uploaded_file in enumerate(uploaded_files):
        file_name = uploaded_file.name
        progress_bar.progress((i + 1) / len(uploaded_files), text=f"Processando: {file_name}")

        with st.status(f"Analisando '{file_name}'...", expanded=False) as status:
            file_extension = os.path.splitext(file_name)[1].lower()
            text = ""
            if file_extension == ".pdf":
                st.write("Lendo arquivo PDF...")
                text = extract_text_from_pdf(uploaded_file)
            elif file_extension in [".png", ".jpg", ".jpeg"]:
                st.write("Lendo arquivo de imagem...")
                text = extract_text_from_image(uploaded_file)
            
            st.write("Extraindo dados do texto...")
            extracted_data = extract_medical_data(text)
            
            if all(v == "Não encontrado" for v in extracted_data.values()):
                status.update(label=f"Nenhum dado encontrado em '{file_name}'", state="warning", expanded=False)
            else:
                status.update(label=f"Extração concluída para '{file_name}'!", state="complete", expanded=False)

            extracted_data["Arquivo"] = file_name
            all_data.append(extracted_data)

            if show_debug_text:
                st.expander(f"📝 Texto bruto extraído de '{file_name}'").text_area("", text, height=250)
    
    progress_bar.empty()

    if all_data:
        df = pd.DataFrame(all_data)[["Arquivo", "Número GUIA", "Registro ANS", "Data de Autorização", "Nome"]]
        st.session_state.processed_data = df

# --- Tabela de Dados Editável e Botões de Download ---
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