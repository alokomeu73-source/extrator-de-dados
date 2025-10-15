# app.py (VERSÃO 8 - COM ANALISTA DE IA INTEGRADO)

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
from datetime import datetime

# Configuração da página do Streamlit
st.set_page_config(
    page_title="Extrator de Guias Médicas com IA",
    page_icon="🤖",
    layout="wide"
)

# Verifica se o Tesseract está instalado
try:
    pytesseract.get_tesseract_version()
except pytesseract.TesseractNotFoundError:
    st.error(
        "Tesseract OCR não foi encontrado. "
        "Certifique-se de que o Tesseract OCR está instalado e acessível no PATH do sistema."
    )
    st.stop()

# ==============================================================================
# 2️⃣ FUNÇÕES DE PROCESSAMENTO DE ARQUIVO E OCR (ESTRUTURADO)
# ==============================================================================

def preprocess_image(image):
    """Aplica pré-processamento para melhorar a qualidade do OCR."""
    img = image.convert('L')  # Converte para escala de cinza
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(2.0) # Aumenta o contraste
    img = img.filter(ImageFilter.SHARPEN) # Aplica nitidez
    return img

def extract_text_from_image(image: Image.Image):
    """
    Extrai texto e suas coordenadas de um objeto de imagem PIL usando Tesseract.
    Retorna um DataFrame do Pandas com dados estruturados.
    """
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

def process_uploaded_file(uploaded_file):
    """
    Processa um arquivo enviado (imagem ou PDF), convertendo-o para um
    DataFrame OCR estruturado. PDFs são rasterizados para imagens.
    """
    file_bytes = io.BytesIO(uploaded_file.read())
    file_name = uploaded_file.name

    try:
        if uploaded_file.type == "application/pdf":
            # Processamento de PDF: converte a primeira página em imagem
            pdf_document = fitz.open(stream=file_bytes, filetype="pdf")
            page = pdf_document.load_page(0)
            pix = page.get_pixmap(dpi=300)
            image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            pdf_document.close()
            return extract_text_from_image(image)
        else:
            # Processamento de Imagem
            image = Image.open(file_bytes)
            return extract_text_from_image(image)
    except Exception as e:
        st.error(f"Erro ao processar o arquivo '{file_name}': {e}")
        return pd.DataFrame()


# ==============================================================================
# 3️⃣ LÓGICA DE EXTRAÇÃO BASEADA EM COORDENADAS (SEM ALTERAÇÕES)
# ==============================================================================

def find_value_near_label(ocr_df, label_pattern, max_distance_x=500):
    """
    Encontra o valor à direita de um rótulo com base em sua posição.
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

    # 1. Número GUIA
    data["Número GUIA"] = find_value_near_label(ocr_df, r'Guia\s*Principal', max_distance_x=250)

    # 2. Registro ANS
    data["Registro ANS"] = find_value_near_label(ocr_df, r'Registro\s*ANS', max_distance_x=200)

    # 3. Data de Autorização
    data["Data de Autorização"] = find_value_near_label(ocr_df, r'Autoriza[çc][ãa]o', max_distance_x=250)
    date_match = re.search(r'(\d{2}/\d{2}/\d{4})', data["Data de Autorização"])
    if date_match:
        data["Data de Autorização"] = date_match.group(1)

    # 4. Nome do Beneficiário
    data["Nome"] = find_value_near_label(ocr_df, r'10\s*-\s*Nome', max_distance_x=600)

    final_data = {
        "Número GUIA": data.get("Número GUIA", "Não encontrado"),
        "Registro ANS": data.get("Registro ANS", "Não encontrado"),
        "Data de Autorização": data.get("Data de Autorização", "Não encontrado"),
        "Nome": data.get("Nome", "Não encontrado"),
    }
    return final_data


# ==============================================================================
# 4️⃣ NOVA SEÇÃO: GERAÇÃO DE ANÁLISE DE FATURAMENTO (IA)
# ==============================================================================

def generate_analysis_report(df):
    """Gera um relatório em Markdown com a análise dos dados extraídos."""
    
    total_guias = len(df)
    if total_guias == 0:
        return "Nenhum dado para analisar."

    # Cálculos dos KPIs
    df_pendencias = df[df.apply(lambda row: row.astype(str).str.contains('Não encontrado').any(), axis=1)]
    guias_com_pendencia = len(df_pendencias)
    guias_completas = total_guias - guias_com_pendencia
    percentual_sucesso = (guias_completas / total_guias) * 100 if total_guias > 0 else 0

    # Análise de campos com falha
    campos_faltantes = {}
    if guias_com_pendencia > 0:
        for col in df.columns:
            if col != 'Arquivo':
                faltantes = df_pendencias[col].astype(str).str.contains('Não encontrado').sum()
                if faltantes > 0:
                    campos_faltantes[col] = faltantes

    # Montagem do Relatório em Markdown
    report = f"""
    # 📊 Relatório de Análise de Faturamento

    **Data da Análise:** {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}

    ---

    ## 1. Resumo Geral e Indicadores Chave (KPIs)

    | Indicador | Valor |
    | :--- | :--- |
    | 📂 **Total de Guias Processadas** | **{total_guias}** |
    | ✅ **Guias Completas (Sem pendências)** | **{guias_completas}** |
    | ⚠️ **Guias com Pendências (Revisão necessária)** | **{guias_com_pendencia}** |
    | 🎯 **Percentual de Sucesso da Extração** | **{percentual_sucesso:.2f}%** |

    ---

    ## 2. Análise Detalhada de Pendências
    """

    if guias_com_pendencia == 0:
        report += "\n🎉 **Excelente!** Nenhuma pendência foi identificada. Todas as guias foram processadas com sucesso."
    else:
        report += f"\nForam identificadas **{guias_com_pendencia} guias** que requerem revisão manual. Abaixo estão os detalhes:\n\n"
        report += "#### Contagem de Falhas por Campo:\n"
        for campo, contagem in campos_faltantes.items():
            report += f"- **{campo}:** {contagem} falha(s)\n"

        report += "\n#### Arquivos que Precisam de Revisão:\n"
        for arquivo in df_pendencias['Arquivo']:
            report += f"- `{arquivo}`\n"

    report += """
    ---

    ## 3. Recomendações e Próximos Passos

    1.  **Ação Imediata:** A equipe de faturamento deve priorizar a revisão manual dos arquivos listados na seção de pendências para garantir a correção dos dados antes do envio.
    2.  **Análise de Causa Raiz:** Analise os arquivos com falhas. Se o problema for a baixa qualidade da digitalização, reforce os padrões de escaneamento. Se for um layout de guia diferente, o sistema pode precisar de ajustes.
    3.  **Processo Concluído:** Após a correção manual na tabela acima, os dados estão prontos para serem exportados para o sistema de faturamento.
    """
    return report

# ==============================================================================
# 5️⃣ Geração de Excel e Interface (COM ADIÇÃO DO ANALISTA)
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
            'fg_color': '#1E90FF', 'font_color': 'white', 'border': 1
        })
        for col_num, value in enumerate(df_to_export.columns.values):
            worksheet.write(0, col_num, value, header_format)
        for idx, col in enumerate(df_to_export):
            series = df_to_export[col]
            max_len = max((series.astype(str).map(len).max(), len(str(series.name)))) + 2
            worksheet.set_column(idx, idx, max_len)
    return output.getvalue()

st.title("🤖 Extrator de Guias Médicas com Analista de IA")
st.markdown("Faça o upload de guias (PDF ou Imagem). O sistema usará OCR e **lógica espacial** para extrair os dados e um **Analista de IA** para gerar um relatório de faturamento.")

# --- BARRA LATERAL ---
with st.sidebar:
    st.image("https://i.imgur.com/3f83NC1.png", width=100)
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
        1. **Faça o upload** de um ou mais arquivos.
        2. **Aguarde** o processamento.
        3. **Revise e edite** os dados na tabela.
        4. **Clique em 'Gerar Relatório'** para uma análise da IA.
        5. **Baixe os resultados** em Excel ou CSV.
        """
    )

# --- LÓGICA PRINCIPAL DA APLICAÇÃO ---
if 'processed_data' not in st.session_state:
    st.session_state.processed_data = pd.DataFrame()

if uploaded_files:
    all_data = []
    progress_bar = st.progress(0, text="Iniciando processamento...")

    for i, uploaded_file in enumerate(uploaded_files):
        file_name = uploaded_file.name
        progress_bar.progress((i + 1) / len(uploaded_files), text=f"Processando: {file_name}")
        
        ocr_dataframe = process_uploaded_file(uploaded_file)

        if not ocr_dataframe.empty:
            if show_debug_text:
                with st.expander(f"🔬 Dados brutos do OCR de '{file_name}'"):
                    st.dataframe(ocr_dataframe)
            
            extracted_data = extract_medical_data_from_structure(ocr_dataframe)
            extracted_data["Arquivo"] = file_name
            all_data.append(extracted_data)
        else:
             st.warning(f"Não foi possível extrair dados do arquivo: {file_name}")


    progress_bar.empty()

    if all_data:
        df = pd.DataFrame(all_data)[["Arquivo", "Número GUIA", "Registro ANS", "Data de Autorização", "Nome"]]
        st.session_state.processed_data = df

# --- EXIBIÇÃO DOS RESULTADOS E DOWNLOADS ---
if not st.session_state.processed_data.empty:
    st.header("📋 Resultados Editáveis")
    st.markdown("Revise os dados extraídos e faça as correções necessárias diretamente na tabela abaixo.")
    
    edited_df = st.data_editor(
        st.session_state.processed_data,
        num_rows="dynamic",
        use_container_width=True,
        key="data_editor"
    )

    st.header("⬇️ Download dos Dados Corrigidos")
    col1, col2 = st.columns(2)
    with col1:
        excel_data = to_excel(edited_df)
        timestamp = datetime.now().strftime("%Y%m%d")
        st.download_button(
            label="📥 Baixar Excel (.xlsx)", data=excel_data,
            file_name=f"guias_medicas_{timestamp}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
    with col2:
        csv_data = edited_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📄 Baixar CSV (.csv)", data=csv_data,
            file_name=f"guias_medicas_{timestamp}.csv",
            mime="text/csv",
            use_container_width=True
        )

    st.divider()

    # --- NOVA SEÇÃO DE ANÁLISE DE IA ---
    st.header("🤖 Análise do Faturamento (Gerada por IA)")
    st.markdown("Após revisar os dados, clique no botão abaixo para que o Analista de IA gere um relatório sobre o lote de guias.")
    
    if st.button("🔍 Gerar Relatório de Análise", use_container_width=True, type="primary"):
        with st.spinner("O Analista de IA está avaliando os dados..."):
            report_md = generate_analysis_report(edited_df)
            st.markdown(report_md)

else:
    st.info("Aguardando o upload de arquivos para iniciar o processamento.")
