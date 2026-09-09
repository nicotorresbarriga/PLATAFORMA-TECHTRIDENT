import streamlit as st
import pandas as pd
import datetime
import os
import time
import smtplib
import imaplib
import re
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from fpdf import FPDF
from streamlit_drawable_canvas import st_canvas
from PIL import Image
import numpy as np
import uuid
import urllib.request
import zipfile
import io
import gc 
from supabase import create_client, Client

st.set_page_config(
    page_title="Plataforma TechTrident",
    page_icon="⚓",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    
    .stApp {
        background: linear-gradient(135deg, #000511 0%, #00122c 50%, #002353 100%);
    }
    h1, h2, h3, p, label, .stMarkdown, span, .stCheckbox label span {
        color: #ffffff !important;
        font-family: 'Inter', sans-serif;
    }
    
    /* Botones 3D Personalizados */
    .stButton>button {
        background: linear-gradient(to bottom, #1a5b9c 0%, #0f3769 100%);
        color: white;
        border-radius: 12px;
        border: 1px solid #0a2445;
        box-shadow: inset 0 2px 0 rgba(255,255,255,0.15), 0 6px 0 #0a2445, 0 8px 12px rgba(0,0,0,0.5);
        transition: all 0.1s ease;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        padding-top: 10px;
        padding-bottom: 10px;
    }
    .stButton>button:hover {
        background: linear-gradient(to bottom, #1e69b3 0%, #12417a 100%);
        box-shadow: inset 0 2px 0 rgba(255,255,255,0.25), 0 6px 0 #0a2445, 0 10px 15px rgba(0,0,0,0.6);
        color: white;
        transform: translateY(-1px);
    }
    .stButton>button:active {
        background: linear-gradient(to bottom, #0f3769 0%, #1a5b9c 100%);
        box-shadow: inset 0 2px 0 rgba(0,0,0,0.1), 0 0px 0 #0a2445, 0 2px 4px rgba(0,0,0,0.4);
        transform: translateY(6px);
    }

    .stTextInput>div>div>input, .stSelectbox>div>div>select, .stTextArea>div>div>textarea, .stNumberInput>div>div>input {
        border-radius: 6px;
        border: 1px solid #0f3769;
        color: #1a202c !important;
        background-color: #f8fafc !important;
        font-weight: 500;
    }
    .stTextInput>div>div>input:disabled {
        background-color: #1e293b !important;
        color: #ffffff !important;
        -webkit-text-fill-color: #ffffff !important;
        opacity: 1 !important;
        border: 1px solid #475569;
    }
    .stRadio>div>label {
        color: #ffffff !important;
    }
    ::placeholder {
        color: #64748b !important;
        opacity: 1;
    }
    
    div[data-testid="stNumberInput"] {
        max-width: 140px !important;
        min-width: 120px !important;
    }
    
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background: linear-gradient(180deg, rgba(15, 55, 105, 0.4) 0%, rgba(10, 36, 69, 0.8) 100%) !important;
        border-radius: 16px !important;
        border: 1px solid #1a5b9c !important;
        padding: 0.5rem !important;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.3) !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

CLAVE_ADMIN = "9926"

@st.cache_resource
def init_connection():
    try:
        url = st.secrets.get("SUPABASE_URL", "")
        key = st.secrets.get("SUPABASE_KEY", "")
        if not url: raise ValueError
    except Exception:
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_KEY", "")
        
    if not url or not key:
        raise ValueError("Credenciales de Supabase no encontradas.")
        
    url = re.sub(r'[\[\]\(\)\s\'"]', '', str(url))
    key = re.sub(r'[\[\]\(\)\s\'"]', '', str(key))
    
    if url.count("http") > 1:
        url = url[:url.find("http", 4)]
        
    return create_client(url, key)

if 'db_usuarios' not in st.session_state: 
    st.session_state.db_usuarios = {
        "Ntorres": {"pass": "17909926", "rut": "17.909.926-8"}, 
        "admin": {"pass": "admin", "rut": "N/A"}
    }
if 'db_centros_areas' not in st.session_state: 
    st.session_state.db_centros_areas = {"Centro Punta Vergara": "Area Austral"}
if 'db_centros_correos' not in st.session_state: 
    st.session_state.db_centros_correos = {"Centro Punta Vergara": "contacto@techtrident.cl"}

if 'db_rovs' not in st.session_state:
    st.session_state.db_rovs = {
        1: {"nombre": "ROV 1", "serie_rov": "12992601117", "serie_ctrl": "12992601117", "mantencion": datetime.date(2026, 8, 2)},
        2: {"nombre": "ROV 2", "serie_rov": "12992601127", "serie_ctrl": "12992601127", "mantencion": datetime.date(2026, 8, 2)}
    }
if 'rov_activo' not in st.session_state:
    st.session_state.rov_activo = 1

if 'historial_mantenciones' not in st.session_state:
    st.session_state.historial_mantenciones = []

CORREOS_OCULTOS = []

RANGOS_INICIO = [f"{str(h).zfill(2)}:{str(m).zfill(2)}" for h in range(6, 12) for m in (0, 30)]  
RANGO_TERMINO = [f"{str(h).zfill(2)}:{str(m).zfill(2)}" for h in range(16, 21) for m in (0, 30)] 
RANGO_DURACION = ["5 minutos", "10 minutos", "15 minutos", "20 minutos", "25 minutos", "30 minutos"]
RANGO_HORA_DIFUSION = [f"{str(h).zfill(2)}:{str(m).zfill(2)}" for h in range(6, 13) for m in (0, 15, 30, 45) if not (h == 12 and m > 0)]

try:
    supabase = init_connection()
except Exception as e:
    st.sidebar.warning(f"⚠️ Advertencia: Conexión Supabase inactiva.")

if 'local_hpt_history' not in st.session_state: st.session_state.local_hpt_history = []
if 'local_reportes_history' not in st.session_state: st.session_state.local_reportes_history = []
if 'local_entrega_history' not in st.session_state: st.session_state.local_entrega_history = []

if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'current_user' not in st.session_state: st.session_state.current_user = ""
if 'current_page' not in st.session_state: st.session_state.current_page = 'login'
if 'hpt_step' not in st.session_state: st.session_state.hpt_step = 1

if 'hpt_pdf_generado' not in st.session_state: st.session_state.hpt_pdf_generado = None
if 'rd_pdf_generado' not in st.session_state: st.session_state.rd_pdf_generado = None

if 'ic_pdf_generado' not in st.session_state: st.session_state.ic_pdf_generado = None
if 'anomalias' not in st.session_state: st.session_state.anomalias = []
if 'ic_data' not in st.session_state: st.session_state.ic_data = {}

if 'hpt_data' not in st.session_state:
    opciones_c = list(st.session_state.db_centros_areas.keys())
    st.session_state.hpt_data = {
        "empresa": "Salmones Blumar Magallanes", "fecha": datetime.date.today(), "hora_inicio": RANGOS_INICIO[2],
        "hora_termino": RANGO_TERMINO[2], "centro": opciones_c[0] if opciones_c else "",
        "correo": "", "encargado": "", "ponton": "", "condicion_puerto": "Abierto", "tarea": "",
        "trabajo_rutinario": "Sí",
        "epp": [False]*7, "faena": "Inspeccion Red pecera", "erc": [False]*6, "tc_duracion": "15 minutos",
        "check_instruido": "Sí", "check_clima": "Sí", "check_equipos": "Sí", "check_orden": "Sí",
        "evidencia_puerto": None, "prevencion_1": "", "prevencion_2": ""
    }
if 'admin_acceso_historial' not in st.session_state: st.session_state.admin_acceso_historial = False
if 'admin_acceso_graficos' not in st.session_state: st.session_state.admin_acceso_graficos = False

def set_page(page_name): st.session_state.current_page = page_name
def set_step(step_number): st.session_state.hpt_step = step_number

def obtener_ruta_logo():
    directorio_actual = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.getcwd()
    posibles = [
        "logo_techtrident.png", "logo_techtrident.PNG", "logo_techtrident.jpg", "Logo_techtrident.png",
        "logo_tridentech.png", "logo_tridentech.PNG", "logo.png",
        os.path.join(directorio_actual, "logo_techtrident.png"),
        os.path.join(directorio_actual, "logo_techtrident.PNG")
    ]
    for p in posibles:
        if os.path.exists(p):
            try:
                with Image.open(p) as img:
                    img.verify()
                return p
            except Exception:
                continue
    return None

def optimizar_imagen_ram(file_bytes_or_path, max_dim=800):
    try:
        if isinstance(file_bytes_or_path, bytes):
            img = Image.open(io.BytesIO(file_bytes_or_path))
        else:
            img = Image.open(file_bytes_or_path)
            
        if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
            img = img.convert('RGB')
            
        img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
        
        output_buffer = io.BytesIO()
        img.save(output_buffer, format='JPEG', quality=75, optimize=True)
        output_buffer.seek(0)
        
        img.close()
        gc.collect() 
        
        return output_buffer.getvalue()
    except Exception as e:
        return file_bytes_or_path if isinstance(file_bytes_or_path, bytes) else open(file_bytes_or_path, "rb").read()

def procesar_firma(canvas_obj, filename):
    if canvas_obj.image_data is not None:
        img_data = canvas_obj.image_data
        firma_img = Image.fromarray((img_data).astype('uint8'), mode='RGBA')
        fondo_blanco = Image.new("RGB", firma_img.size, (255, 255, 255))
        fondo_blanco.paste(firma_img, mask=firma_img.split()[3])
        fondo_blanco.save(filename)
        return True
    return False

def generar_pdf_consolidado(datos, anomalias, logo_filename, rov_cover, nombre_archivo):
    pdf = FPDF(orientation='P', unit='mm', format='A4')
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # PÁGINA 1: PORTADA
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.set_text_color(15, 55, 105) 
    pdf.cell(60, 10, "TECHTRIDENT", border=0, align='L')
    pdf.cell(70, 10, "ÁREA ROBÓTICA", border=0, align='C')
    pdf.set_text_color(0, 102, 204) 
    cliente_str = str(datos.get("cliente", "CLIENTE")).upper()
    pdf.cell(60, 10, cliente_str[:20], border=0, align='R', ln=True)
    pdf.line(10, 22, 200, 22)
    pdf.ln(10)
    
    if rov_cover and os.path.exists(rov_cover):
        try:
            pdf.image(rov_cover, x=25, y=30, w=160)
            pdf.set_y(120) 
        except:
            pdf.set_y(60)
    else:
        pdf.set_y(60)
        
    pdf.set_font("Arial", 'B', 24)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 10, "INFORME DIARIO", border=0, ln=True, align='C')
    pdf.set_font("Arial", 'B', 18)
    pdf.cell(0, 10, "INSPECCIÓN ROBÓTICA SUBMARINA", border=0, ln=True, align='C')
    centro_str = str(datos.get("centro", "CENTRO")).upper()
    pdf.cell(0, 10, f"CENTRO {centro_str}", border=0, ln=True, align='C')
    pdf.ln(10)
    
    pdf.set_left_margin(25)
    pdf.set_right_margin(25)
    pdf.set_x(25)
    
    def add_cover_row(label, value):
        pdf.set_font("Arial", 'B', 10)
        pdf.set_fill_color(240, 240, 240)
        pdf.cell(70, 8, f"  {label}", border=1, fill=True)
        pdf.set_font("Arial", '', 10)
        pdf.cell(90, 8, f"  {str(value)[:45]}", border=1, ln=True)

    add_cover_row("CLIENTE", datos.get("cliente", ""))
    add_cover_row("CENTRO", datos.get("centro", ""))
    add_cover_row("ENCARGADO DE CENTRO", datos.get("encargado", ""))
    add_cover_row("FECHA", datos.get("fecha", ""))
    add_cover_row("PILOTO ROV", datos.get("piloto", ""))
    add_cover_row("DISPONIBILIDAD", datos.get("disponibilidad", "Disponible"))
    add_cover_row("EQUIPO ROV", datos.get("equipo", ""))
    
    metricas_str = f"Trabajados: {datos.get('dias_trabajados', 1)} | P. Cerrado: {datos.get('dias_cerrado', 0)} | Fallas: {datos.get('dias_fallas', 0)}"
    add_cover_row("DÍAS OPERATIVOS", metricas_str)
    equipos_str = f"Backup: {datos.get('backup', 'SI')} | Grabber: {datos.get('graber', 'SI')}"
    add_cover_row("ESTADO DE EQUIPOS", equipos_str)
    
    pdf.set_y(-25)
    pdf.set_left_margin(10)
    pdf.set_right_margin(10)
    pdf.set_font("Arial", 'B', 8)
    pdf.set_text_color(15, 55, 105)
    pdf.cell(0, 5, "TECHTRIDENT ÁREA ROBÓTICA - CONTACTO@TECHTRIDENT.CL", align='C', ln=True)

    # PÁGINA 2: PLANIMETRÍA Y ACTIVIDADES
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 10, "ESPECIFICACIÓN DEL CENTRO E INSPECCIÓN", border=0, ln=True, align='C')
    pdf.ln(5)
    
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(0, 6, "ACTIVIDADES REALIZADAS:", ln=True)
    pdf.set_font("Arial", '', 10)
    act_am = str(datos.get("actividad_am", "")).encode('latin-1', 'replace').decode('latin-1')
    act_pm = str(datos.get("actividad_pm", "")).encode('latin-1', 'replace').decode('latin-1')
    obs = str(datos.get("observaciones", "")).encode('latin-1', 'replace').decode('latin-1')
    
    pdf.multi_cell(0, 5, f"AM: {act_am}")
    pdf.multi_cell(0, 5, f"PM: {act_pm}")
    pdf.ln(3)
    pdf.multi_cell(0, 5, f"Observaciones de la jornada: {obs}")
    pdf.ln(10)
    
    if datos.get("planimetria"):
        try:
            temp_path = f"temp_pl_{uuid.uuid4().hex[:6]}.jpg"
            bytes_opt = optimizar_imagen_ram(datos["planimetria"], max_dim=1200)
            with open(temp_path, "wb") as f: f.write(bytes_opt)
            with Image.open(temp_path) as pil_img:
                w, h = pil_img.size
                aspect = h / w
                w_mm = 170
                h_mm = w_mm * aspect
                if h_mm > 160:
                    h_mm = 160
                    w_mm = h_mm / aspect
            pdf.image(temp_path, x=(210-w_mm)/2, y=pdf.get_y(), w=w_mm, h=h_mm)
            pdf.set_y(pdf.get_y() + h_mm + 10)
            os.remove(temp_path)
        except Exception as e:
            pdf.set_font("Arial", 'I', 10)
            pdf.cell(0, 10, "(No se adjuntó esquema válido o no se pudo procesar)", ln=True, align='C')

    # PÁGINAS 3+: GRILLA DE FOTOGRAFÍAS
    if anomalias:
        anomalias_por_jaula = {}
        for a in anomalias:
            j = a.get('jaula', 'N/A')
            if j not in anomalias_por_jaula:
                anomalias_por_jaula[j] = []
            anomalias_por_jaula[j].append(a)
            
        for jaula, lista_anomalias in anomalias_por_jaula.items():
            pdf.add_page()
            pdf.set_font("Arial", 'B', 16)
            pdf
