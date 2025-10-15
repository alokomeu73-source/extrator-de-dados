# app.py (VERSÃO 7 - REESTRUTURADO COM LÓGICA ESPACIAL)

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

# Configuração da página do Streamlit
st.set_page_config(
    page_title="Extrator de Guias Médicas",
    page_icon="🩺",
    layout="wide"
)

# Verifica se o Tesseract está instalado
try:
    pytesseract.get_tesseract_version()
except pytesseract.TesseractNotFoundError:
    st.error(
        "Tesseract OCR não foi encontrado. "
        "Certifique-se de que o arquivo 'packages.txt' com 'tesseract-ocr' "
        "está no seu repositório do GitHub."
    )

# ==============================================================================
# 2️⃣ FUNÇÕES DE OCR E PROCESSAMENTO DE IMAGEM (ESTRUTURADO)
# ==============================================================================

def preprocess_image(image):
    """Aplica pré-processamento para melhorar a qualidade do OCR."""
    img = image.convert('L')  # Converte para escala de cinza
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(2.0) # Aumenta o contraste
    img = img.filter(ImageFilter.SHARPEN) # Aplica nitidez
    return img

def extract_structured_data_from_image(file_object):
    """
    Extrai texto e suas coordenadas de uma imagem usando Tesseract.
    Retorna um DataFrame do Pandas com dados estruturados.
    """
    try:
        image = Image.open(file_object)
        processed_image = preprocess_image(image)
        # Usa image_to_data para obter texto, coordenadas e confiança
        ocr_df = pytesseract.image_to_data(
            processed_image, 
            lang='por', 
            output_type=pytesseract.Output.DATAFRAME
        )
        # Filtra palavras vazias ou com baixa confiança
        ocr_df.dropna(subset=['text'], inplace=True)
        ocr_df = ocr_df[ocr_df['conf'] > 30]
        ocr_df['text'] = ocr_df['text'].str.strip()
        ocr_df = ocr_df[ocr_df['text'] != '']
        return ocr_df
    except Exception as e:
        st.error(f"Erro ao processar a imagem com Tesseract: {e}")
        return pd.DataFrame()

# ==============================================================================
# 3️⃣ NOVA LÓGICA DE EXTRAÇÃO BASEADA EM COORDENADAS
# ==============================================================================

def find_value_near_label(ocr_df, label_pattern, max_distance_x=500):
    """
    Encontra o valor à direita de um rótulo com base em sua posição.

    Args:
        ocr_df (pd.DataFrame): DataFrame com os dados do Tesseract.
        label_pattern (str): Padrão RegEx para encontrar o rótulo.
        max_distance_x (int): A distância máxima (em pixels) para procurar à direita.

    Returns:
        str: O valor encontrado ou "Não encontrado".
    """
    try:
        # Encontra a(s) parte(s) do rótulo
        label_rows = ocr_df[ocr_df['text'].str.contains(label_pattern, na=False, flags=re.IGNORECASE)]
        if label_rows.empty:
            return "Não encontrado"

        # Pega as coordenadas da primeira ocorrência do rótulo
        label_row = label_rows.iloc[0]
        label_x = label_row['left'] + label_row['width']
        label_y_center = label_row['top'] + label_row['height'] / 2

        # Define a área de busca para o valor (mesma linha, à direita)
        search_top = label_y_center - label_row['height']
        search_bottom = label_y_center + label_row['height']
        search_left = label_x
        search_right = label_x + max_distance_x

        # Filtra as palavras candidatas que estão na área de busca
        value_df = ocr_df[
            (ocr_df['top'] >= search_top) &
            (ocr_df['top'] <= search_bottom) &
            (ocr_df['left'] >= search_left) &
            (ocr_df['left'] <= search_right)
        ]

        if value_df.empty:
            return "Não encontrado"
        
        # Ordena as palavras por sua posição horizontal e junta o texto
        value_df = value_df.sort_values(by='left')
        found_value = ' '.join(value_df['text'].astype(str))
        
        return found_value.strip()
        
    except Exception:
        return "Não encontrado"

def extract_medical_data_from_structure(ocr_df):
    """Função principal que orquestra a extração usando a lógica espacial."""
    if ocr_df.empty:
        return {
            "Número GUIA": "OCR falhou", "Registro ANS": "OCR falhou",
            "Data de Autorização": "OCR falhou", "Nome": "OCR falhou"
        }
    
    data = {}
    
    # --- Definição dos Rótulos e Busca ---
    
    # 1. Número GUIA (Rótulo: "2 - Número Guia")
    data["Número GUIA"] = find_value_near_label(ocr_df, r'\b2\s*-\s*N[úu]mero\s*Guia\b', max_distance_x=200)

    # 2. Registro ANS (Rótulo: "1 - Registro ANS")
    data["Registro ANS"] = find_value_near_label(ocr_df, r'Registro\s*ANS', max_distance_x=200)

    # 3. Data de Autorização (Rótulo: "3 - Data de Autorização")
    data["Data de Autorização"] = find_value_near_label(ocr_df, r'Autoriza[çc][ãa]o', max_distance_x=250)
    # Limpeza para pegar apenas o padrão de data
    date_match = re.search(r'(\d{2}/\d{2}/\d{4})', data["Data de Autorização"])
    if date_match:
        data["Data de Autorização"] = date_match.group(1)

    # 4. Nome do Beneficiário (Rótulo: "10 - Nome")
    data["Nome"] = find_value_near_label(ocr_df, r'\b10\s*-\s*Nome\b', max_distance_x=600)

    # Garante que todos os campos existam no dicionário final
    final_data = {
        "Número GUIA": data.get("Número GUIA", "Não encontrado"),
        "Registro ANS": data.get("Registro ANS", "Não encontrado"),
        "Data de Autorização": data.get("Data de Autorização", "Não encontrado"),
        "Nome": data.get("Nome", "Não encontrado"),
    }

    return final_data


# ==============================================================================
# 4️⃣ Geração de Excel e Interface (Sem alterações)
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

st.title("🩺 Extrator de Informações de Guias Médicas (V7)")
st.markdown("Faça o upload de guias em formato PDF ou imagem. O sistema usará OCR e **lógica espacial** para extrair os dados com alta precisão.")

with st.sidebar:
    st.header("📤 Upload de Arquivos")
    uploaded_files = st.file_uploader(
        "Selecione as guias (PDF, PNG, JPG)",
        type=["pdf", "png", "jpg", "jpeg"],
        accept_multiple_files=True
    )
    st.header("🛠️ Opções")
    show_debug_text = st.checkbox("Mostrar dados brutos do OCR (debug)")

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
            uploaded_file.seek(0)
            file_io = io.BytesIO(uploaded_file.read())

            with st.status(f"Analisando '{file_name}'...", expanded=True) as status:
                st.write("Extraindo texto e coordenadas do arquivo...")
                # A extração agora retorna um DataFrame estruturado
                ocr_dataframe = extract_structured_data_from_image(file_io)

                if show_debug_text:
                    st.expander(f"🔬 Dados brutos do OCR de '{file_name}'").dataframe(ocr_dataframe)

                st.write("Aplicando lógica espacial para encontrar os dados...")
                extracted_data = extract_medical_data_from_structure(ocr_dataframe)

                if all(v == "Não encontrado" or v == "OCR falhou" for v in extracted_data.values()):
                    status.update(label=f"Nenhum dado encontrado em '{file_name}'", state="error", expanded=True)
                else:
                    status.update(label=f"Extração concluída para '{file_name}'!", state="complete", expanded=False)

                extracted_data["Arquivo"] = file_name
                all_data.append(extracted_data)

        except Exception as e:
            st.error(f"Erro crítico ao processar '{file_name}'. Detalhe: {e}")

    progress_bar.empty()

    if all_data:
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
            label="📥 Baixar Excel", data=excel_data,
            file_name=f"guias_medicas_{timestamp}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
    with col2:
        csv_data = edited_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📄 Baixar CSV", data=csv_data,
            file_name=f"guias_medicas_{timestamp}.csv",
            mime="text/csv",
            use_container_width=True
        )
else:
    st.info("Aguardando o upload de arquivos para iniciar o processamento.")
