import streamlit as st
import pandas as pd
import datetime
from zoneinfo import ZoneInfo
import os
import time
import smtplib
import imaplib
import re
import pickle
import inspect
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

# ==============================================================================
# 1. CONFIGURACIÓN DE PÁGINA Y ESTILOS VISUALES
# ==============================================================================
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
    h1, h2, h3, h4, p, label, .stMarkdown, span, .stCheckbox label span {
        color: #ffffff !important;
        font-family: 'Inter', sans-serif;
    }
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
        box-shadow: inset 0 2px 0 rgba(255,255,255,0.1), 0 0px 0 #0a2445, 0 2px 4px rgba(0,0,0,0.4);
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
        padding: 0.75rem !important;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.3) !important;
    }
    div[data-testid="stMetricValue"] {
        color: #38bdf8 !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

CLAVE_ADMIN = "9926"
ARCHIVO_BORRADORES = "borradores_hpt_techtrident.pkl"
ARCHIVO_ESTADO_APP = "estado_operativo_techtrident.pkl"
DIAS_ROTACION_ROV = 7

# ==============================================================================
# 2. UTILIDADES DE FECHA, CONEXIÓN Y PERSISTENCIA
# ==============================================================================
def obtener_hora_chile():
    """Retorna la fecha y hora oficial de Chile ajustando horario de invierno/verano."""
    try:
        return datetime.datetime.now(ZoneInfo("America/Santiago"))
    except Exception:
        return datetime.datetime.utcnow() - datetime.timedelta(hours=3)

def limpiar_texto_pdf(texto):
    """Convierte texto a latin-1 seguro para FPDF evitando errores de codificación."""
    if texto is None:
        return ""
    return str(texto).encode("latin-1", "replace").decode("latin-1")

def val_seguro(dic, clave, defecto="Sin registro"):
    """Retorna un texto limpio evitando mostrar None, NaN o vacíos."""
    if not isinstance(dic, dict):
        return defecto
    val = dic.get(clave, None)
    if val is None:
        return defecto
    try:
        if pd.isna(val):
            return defecto
    except Exception:
        pass
    txt = str(val).strip()
    if not txt or txt.lower() in ("none", "nan", "null"):
        return defecto
    return txt

def limpiar_df_vista(df, col_url="url_documento"):
    """Reemplaza valores None/NaN/vacíos por '—' para evitar 'None' en tablas."""
    df_clean = df.copy()
    for col in df_clean.columns:
        if col == col_url:
            df_clean[col] = df_clean[col].apply(
                lambda x: str(x).strip() if pd.notnull(x) and str(x).strip().startswith("http") else None
            )
        else:
            df_clean[col] = df_clean[col].apply(
                lambda x: "—" if (x is None or (isinstance(x, float) and pd.isna(x)) or str(x).strip().lower() in ("", "none", "nan", "null")) else str(x)
            )
    return df_clean

def crear_canvas_firma(**kwargs):
    """Wrapper compatible con streamlit-drawable-canvas 0.9.x y 0.10.x+."""
    try:
        sig = inspect.signature(st_canvas)
        if "return_image_data" in sig.parameters:
            kwargs["return_image_data"] = True
        else:
            kwargs.pop("return_image_data", None)
    except Exception:
        kwargs.pop("return_image_data", None)
    return st_canvas(**kwargs)

@st.cache_resource
def init_connection():
    try:
        url = st.secrets.get("SUPABASE_URL", "")
        key = st.secrets.get("SUPABASE_KEY", "")
        if not url:
            raise ValueError("Secret vacío")
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

@st.cache_resource
def obtener_almacen_borradores():
    if os.path.exists(ARCHIVO_BORRADORES):
        try:
            with open(ARCHIVO_BORRADORES, "rb") as f:
                return pickle.load(f)
        except Exception:
            return {}
    return {}

def guardar_borrador_usuario(usuario, step, data):
    borradores = obtener_almacen_borradores()
    borradores[usuario] = {
        "step": step,
        "data": data.copy(),
        "guardado_el": obtener_hora_chile().strftime("%d-%m-%Y %H:%M")
    }
    try:
        with open(ARCHIVO_BORRADORES, "wb") as f:
            pickle.dump(borradores, f)
    except Exception:
        pass

def eliminar_borrador_usuario(usuario):
    borradores = obtener_almacen_borradores()
    if usuario in borradores:
        del borradores[usuario]
        try:
            with open(ARCHIVO_BORRADORES, "wb") as f:
                pickle.dump(borradores, f)
        except Exception:
            pass

def cargar_estado_persistente():
    if os.path.exists(ARCHIVO_ESTADO_APP):
        try:
            with open(ARCHIVO_ESTADO_APP, "rb") as f:
                return pickle.load(f)
        except Exception:
            return {}
    return {}

def guardar_estado_persistente():
    payload = {
        "db_usuarios": st.session_state.get("db_usuarios", {}),
        "db_centros_areas": st.session_state.get("db_centros_areas", {}),
        "db_centros_correos": st.session_state.get("db_centros_correos", {}),
        "db_centros_fin_faena": st.session_state.get("db_centros_fin_faena", {}),
        "db_rovs_por_centro": st.session_state.get("db_rovs_por_centro", {}),
        "historial_mantenciones": st.session_state.get("historial_mantenciones", []),
        "historial_rotaciones": st.session_state.get("historial_rotaciones", []),
        "local_entrega_history": st.session_state.get("local_entrega_history", []),
    }
    try:
        with open(ARCHIVO_ESTADO_APP, "wb") as f:
            pickle.dump(payload, f)
    except Exception:
        pass

def obtener_datos_demo_entregas():
    """Genera registros realistas de demostración para mostrar alertas y gráficos al jefe."""
    hoy = obtener_hora_chile().date()
    return [
        {
            "id": "demo-1",
            "fecha": str(hoy - datetime.timedelta(days=1)),
            "usuario": "Ntorres",
            "piloto_entrante": "Jrojas",
            "centro": "Centro Punta Vergara",
            "area": "Área Austral",
            "tipo_reporte": "Entrega de Turno",
            "rov_en_uso": "ROV 1 (S/N: 12992601117)",
            "estado_rov": "Bueno",
            "estado_controlador": "Bueno",
            "estado_umbilical": "Requiere cambio",
            "estado_equipamiento": "Bueno",
            "herramientas_faltantes": ["Pelacables"],
            "materiales_faltantes": ["Tubos de grasa dieléctrica (Loctite)", "WD-40"],
            "alertas_centro": "Cable umbilical con corte superficial en los primeros 15 metros, requiere reemplazo urgente.",
            "tareas_pendientes": "Revisar conectores de carga y cambiar umbilical antes de inmersión en jaula 104.",
            "faena_realizada": "Inspección red pecera y lobera módulos 100 y 200.",
            "url_documento": None,
            "es_demo": True
        },
        {
            "id": "demo-2",
            "fecha": str(hoy - datetime.timedelta(days=2)),
            "usuario": "Mgonzalez",
            "piloto_entrante": "Csilva",
            "centro": "Centro Rowlett",
            "area": "Área Magallanes",
            "tipo_reporte": "Entrega de Turno",
            "rov_en_uso": "ROV 1 (S/N: 12992602201)",
            "estado_rov": "Requiere cambio",
            "estado_controlador": "Regular",
            "estado_umbilical": "Bueno",
            "estado_equipamiento": "Regular",
            "herramientas_faltantes": [],
            "materiales_faltantes": ["Rollo de cinta de empalme (Splicing tape)"],
            "alertas_centro": "Propulsor vertical trasero del ROV 1 con vibración anómala y pérdida de potencia.",
            "tareas_pendientes": "Enviar ROV 1 a taller central y operar con ROV 2 Stand-by.",
            "faena_realizada": "Extracción de mortalidad e inspección de tensores.",
            "url_documento": None,
            "es_demo": True
        },
        {
            "id": "demo-3",
            "fecha": str(hoy - datetime.timedelta(days=4)),
            "usuario": "Dfuentes",
            "piloto_entrante": "Rparedes",
            "centro": "Centro Melinka",
            "area": "Área Aysén",
            "tipo_reporte": "Entrega de Turno",
            "rov_en_uso": "ROV 2 (S/N: 12992603302)",
            "estado_rov": "Regular",
            "estado_controlador": "Bueno",
            "estado_umbilical": "Regular",
            "estado_equipamiento": "Requiere cambio",
            "herramientas_faltantes": ["Cuchillo de maniobra con funda (Bahco)", "Alicate de corte diagonal"],
            "materiales_faltantes": ["Frasco de vaselina", "Tapones para puerto de carga", "Limpia contacto"],
            "alertas_centro": "Carpa plegable rasgada por temporal de viento; falta stock de insumos básicos de mantención.",
            "tareas_pendientes": "Solicitar reposición urgente de insumos y cambio de carpa.",
            "faena_realizada": "Apoyo a centro de cultivo y recuperación inorgánicos.",
            "url_documento": None,
            "es_demo": True
        },
        {
            "id": "demo-4",
            "fecha": str(hoy - datetime.timedelta(days=9)),
            "usuario": "Mgonzalez",
            "piloto_entrante": "Csilva",
            "centro": "Centro Rowlett",
            "area": "Área Magallanes",
            "tipo_reporte": "Entrega de Turno",
            "rov_en_uso": "ROV 2 (S/N: 12992602202)",
            "estado_rov": "Bueno",
            "estado_controlador": "Requiere cambio",
            "estado_umbilical": "Requiere cambio",
            "estado_equipamiento": "Bueno",
            "herramientas_faltantes": [],
            "materiales_faltantes": ["Adhesivo industrial B-7000"],
            "alertas_centro": "Joystick derecho del controlador presenta deriva continua; umbilical con peladura.",
            "tareas_pendientes": "Calibrar o reemplazar controlador.",
            "faena_realizada": "Inspección completa de redes loberas.",
            "url_documento": None,
            "es_demo": True
        },
        {
            "id": "demo-5",
            "fecha": str(hoy - datetime.timedelta(days=3)),
            "usuario": "Lvera",
            "piloto_entrante": "Amunoz",
            "centro": "Centro Skyring",
            "area": "Área Magallanes",
            "tipo_reporte": "Entrega de Turno",
            "rov_en_uso": "ROV 1 (S/N: 12992604401)",
            "estado_rov": "Bueno",
            "estado_controlador": "Bueno",
            "estado_umbilical": "Bueno",
            "estado_equipamiento": "Bueno",
            "herramientas_faltantes": [],
            "materiales_faltantes": [],
            "alertas_centro": "",
            "tareas_pendientes": "Continuar inspección preventiva módulo 300.",
            "faena_realizada": "Operación normal sin novedades.",
            "url_documento": None,
            "es_demo": True
        }
    ]

# ==============================================================================
# 3. INICIALIZACIÓN DE ESTADOS Y BASES DE DATOS
# ==============================================================================
estado_guardado = cargar_estado_persistente()
hoy_cl = obtener_hora_chile().date()

if "db_usuarios" not in st.session_state:
    st.session_state.db_usuarios = estado_guardado.get("db_usuarios") or {
        "admin": {"pass": "admin", "rut": "N/A", "rol": "admin", "centro": "Todos"},
        "Ntorres": {"pass": "17909926", "rut": "17.909.926-8", "rol": "piloto", "centro": "Centro Punta Vergara"},
        "Jrojas": {"pass": "1234", "rut": "18.452.110-3", "rol": "piloto", "centro": "Centro Punta Vergara"},
        "Mgonzalez": {"pass": "1234", "rut": "16.820.331-2", "rol": "piloto", "centro": "Centro Rowlett"},
        "Dfuentes": {"pass": "1234", "rut": "19.104.552-K", "rol": "piloto", "centro": "Centro Melinka"},
    }
else:
    for u, info in st.session_state.db_usuarios.items():
        if "rol" not in info:
            info["rol"] = "admin" if u == "admin" else "piloto"
        if "centro" not in info:
            info["centro"] = "Todos" if u == "admin" else "Centro Punta Vergara"

if "db_centros_areas" not in st.session_state:
    st.session_state.db_centros_areas = estado_guardado.get("db_centros_areas") or {
        "Centro Punta Vergara": "Área Austral",
        "Centro Rowlett": "Área Magallanes",
        "Centro Melinka": "Área Aysén",
        "Centro Skyring": "Área Magallanes",
        "Centro Chacabuco": "Área Aysén",
    }

if "db_centros_correos" not in st.session_state:
    st.session_state.db_centros_correos = estado_guardado.get("db_centros_correos") or {
        "Centro Punta Vergara": "contacto@techtrident.cl",
        "Centro Rowlett": "operaciones.rowlett@incinel.cl",
        "Centro Melinka": "operaciones.melinka@incinel.cl",
        "Centro Skyring": "operaciones.skyring@incinel.cl",
        "Centro Chacabuco": "operaciones.chacabuco@incinel.cl",
    }

if "db_centros_fin_faena" not in st.session_state:
    st.session_state.db_centros_fin_faena = estado_guardado.get("db_centros_fin_faena") or {
        "Centro Punta Vergara": hoy_cl + datetime.timedelta(days=5),
        "Centro Rowlett": hoy_cl + datetime.timedelta(days=2),
        "Centro Melinka": hoy_cl + datetime.timedelta(days=6),
        "Centro Skyring": hoy_cl + datetime.timedelta(days=4),
        "Centro Chacabuco": hoy_cl,  # Hoy es último día de faena y aún sin entrega -> genera alerta automática
    }

if "db_rovs_por_centro" not in st.session_state:
    st.session_state.db_rovs_por_centro = estado_guardado.get("db_rovs_por_centro") or {
        "Centro Punta Vergara": {
            "activo_id": 1,
            "equipos": {
                1: {
                    "nombre": "ROV 1",
                    "serie_rov": "12992601117",
                    "serie_ctrl": "12992601117",
                    "mantencion": hoy_cl - datetime.timedelta(days=12),
                    "fecha_inicio_uso": hoy_cl - datetime.timedelta(days=7),
                },
                2: {
                    "nombre": "ROV 2",
                    "serie_rov": "12992601127",
                    "serie_ctrl": "12992601127",
                    "mantencion": hoy_cl - datetime.timedelta(days=5),
                    "fecha_inicio_uso": hoy_cl - datetime.timedelta(days=14),
                },
            },
        },
        "Centro Rowlett": {
            "activo_id": 1,
            "equipos": {
                1: {
                    "nombre": "ROV 1",
                    "serie_rov": "12992602201",
                    "serie_ctrl": "12992602201",
                    "mantencion": hoy_cl - datetime.timedelta(days=18),
                    "fecha_inicio_uso": hoy_cl - datetime.timedelta(days=9),
                },
                2: {
                    "nombre": "ROV 2",
                    "serie_rov": "12992602202",
                    "serie_ctrl": "12992602202",
                    "mantencion": hoy_cl - datetime.timedelta(days=4),
                    "fecha_inicio_uso": hoy_cl - datetime.timedelta(days=16),
                },
            },
        },
    }

def asegurar_rovs_centro(centro_nombre):
    """Garantiza que cualquier centro tenga una estructura de ROVs inicializada."""
    if centro_nombre not in st.session_state.db_rovs_por_centro:
        st.session_state.db_rovs_por_centro[centro_nombre] = {
            "activo_id": 1,
            "equipos": {
                1: {
                    "nombre": "ROV 1",
                    "serie_rov": "Por asignar",
                    "serie_ctrl": "Por asignar",
                    "mantencion": obtener_hora_chile().date(),
                    "fecha_inicio_uso": obtener_hora_chile().date(),
                },
                2: {
                    "nombre": "ROV 2",
                    "serie_rov": "Por asignar",
                    "serie_ctrl": "Por asignar",
                    "mantencion": obtener_hora_chile().date(),
                    "fecha_inicio_uso": obtener_hora_chile().date(),
                },
            },
        }
    return st.session_state.db_rovs_por_centro[centro_nombre]

if "historial_mantenciones" not in st.session_state:
    st.session_state.historial_mantenciones = estado_guardado.get("historial_mantenciones", [])
if "historial_rotaciones" not in st.session_state:
    st.session_state.historial_rotaciones = estado_guardado.get("historial_rotaciones", [])

CORREOS_OCULTOS = []
RANGOS_INICIO = [f"{str(h).zfill(2)}:{str(m).zfill(2)}" for h in range(6, 12) for m in (0, 30)]
RANGO_TERMINO = [f"{str(h).zfill(2)}:{str(m).zfill(2)}" for h in range(16, 21) for m in (0, 30)]
RANGO_DURACION = ["5 minutos", "10 minutos", "15 minutos", "20 minutos", "25 minutos", "30 minutos"]
RANGO_HORA_DIFUSION = [f"{str(h).zfill(2)}:{str(m).zfill(2)}" for h in range(6, 13) for m in (0, 15, 30, 45) if not (h == 12 and m > 0)]

supabase = None
try:
    supabase = init_connection()
except Exception:
    supabase = None

if "local_hpt_history" not in st.session_state:
    st.session_state.local_hpt_history = []
if "local_reportes_history" not in st.session_state:
    st.session_state.local_reportes_history = []
if "local_entrega_history" not in st.session_state:
    st.session_state.local_entrega_history = estado_guardado.get("local_entrega_history", [])

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "current_user" not in st.session_state:
    st.session_state.current_user = ""
if "current_page" not in st.session_state:
    st.session_state.current_page = "login"
if "admin_view_mode" not in st.session_state:
    st.session_state.admin_view_mode = "gerencia"  # 'gerencia' | 'piloto_demo' | 'suite_completa'
if "usar_datos_demo" not in st.session_state:
    st.session_state.usar_datos_demo = False
if "centro_piloto_activo" not in st.session_state:
    st.session_state.centro_piloto_activo = "Centro Punta Vergara"
if "hpt_step" not in st.session_state:
    st.session_state.hpt_step = 1
if "hpt_pdf_generado" not in st.session_state:
    st.session_state.hpt_pdf_generado = None
if "rd_pdf_generado" not in st.session_state:
    st.session_state.rd_pdf_generado = None
if "ic_pdf_generado" not in st.session_state:
    st.session_state.ic_pdf_generado = None
if "anomalias" not in st.session_state:
    st.session_state.anomalias = []
if "ic_data" not in st.session_state:
    st.session_state.ic_data = {}
if "historial_reportes_correo" not in st.session_state:
    st.session_state.historial_reportes_correo = []
if "reset_firma_piloto_hpt" not in st.session_state:
    st.session_state.reset_firma_piloto_hpt = 0
if "reset_firma_encargado_hpt" not in st.session_state:
    st.session_state.reset_firma_encargado_hpt = 0
if "admin_acceso_historial" not in st.session_state:
    st.session_state.admin_acceso_historial = False
if "admin_acceso_graficos" not in st.session_state:
    st.session_state.admin_acceso_graficos = False

if "hpt_data" not in st.session_state:
    opciones_c = list(st.session_state.db_centros_areas.keys())
    st.session_state.hpt_data = {
        "empresa": "Salmones Blumar Magallanes",
        "fecha": obtener_hora_chile().date(),
        "hora_inicio": RANGOS_INICIO[2],
        "hora_termino": RANGO_TERMINO[2],
        "centro": opciones_c[0] if opciones_c else "",
        "correo": "",
        "encargado": "",
        "ponton": "",
        "condicion_puerto": "Abierto",
        "tarea": "",
        "trabajo_rutinario": "Sí",
        "epp": [False] * 7,
        "faena": "Inspeccion Red pecera",
        "erc": [False] * 6,
        "tc_duracion": "15 minutos",
        "tc_hora": "07:45",
        "tc_nombre": "Faena diaria",
        "tc_fecha": obtener_hora_chile().date(),
        "check_instruido": "Sí",
        "check_clima": "Sí",
        "check_equipos": "Sí",
        "check_orden": "Sí",
        "evidencia_puerto": None,
        "prevencion_1": "",
        "prevencion_2": "",
    }

def set_page(page_name):
    st.session_state.current_page = page_name

def set_step(step_number):
    st.session_state.hpt_step = step_number

def es_administrador():
    user = st.session_state.get("current_user", "")
    info = st.session_state.db_usuarios.get(user, {})
    return user == "admin" or info.get("rol") == "admin"

def obtener_centro_usuario():
    user = st.session_state.get("current_user", "")
    centros = list(st.session_state.db_centros_areas.keys())
    default_c = centros[0] if centros else "Centro Punta Vergara"
    if es_administrador():
        c = st.session_state.get("centro_piloto_activo", default_c)
        return c if c in centros else default_c
    info = st.session_state.db_usuarios.get(user, {})
    c = info.get("centro", default_c)
    return c if c in centros else default_c

def obtener_ruta_logo():
    directorio_actual = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
    posibles = [
        "logo_techtrident.png", "logo_techtrident.PNG", "logo_techtrident.jpg",
        "Logo_techtrident.png", "logo_tridentech.png", "logo_tridentech.PNG",
        "logo_tridentech.jpg", "logo.png",
        os.path.join(directorio_actual, "logo_techtrident.png"),
        os.path.join(directorio_actual, "logo_tridentech.png"),
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
        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            img = img.convert("RGB")
        img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
        output_buffer = io.BytesIO()
        img.save(output_buffer, format="JPEG", quality=75, optimize=True)
        output_buffer.seek(0)
        img.close()
        gc.collect()
        return output_buffer.getvalue()
    except Exception:
        if isinstance(file_bytes_or_path, bytes):
            return file_bytes_or_path
        with open(file_bytes_or_path, "rb") as f:
            return f.read()

def procesar_firma(canvas_obj, filename):
    if canvas_obj is not None and getattr(canvas_obj, "image_data", None) is not None:
        img_data = canvas_obj.image_data
        firma_img = Image.fromarray(img_data.astype("uint8"), mode="RGBA")
        fondo_blanco = Image.new("RGB", firma_img.size, (255, 255, 255))
        fondo_blanco.paste(firma_img, mask=firma_img.split()[3])
        fondo_blanco.save(filename)
        return True
    return False

def obtener_todas_las_entregas(incluir_demo=False):
    """Combina entregas desde Supabase + respaldo local detallado (+ demo opcional)."""
    registros_combinados = []
    claves_vistas = set()

    # 1. Locales detallados primero (tienen todos los campos ricos)
    for r in reversed(st.session_state.local_entrega_history):
        clave = (str(r.get("fecha", "")), str(r.get("centro", "")), str(r.get("usuario", "")), str(r.get("url_documento", "")))
        if clave not in claves_vistas:
            claves_vistas.add(clave)
            registros_combinados.append(r)

    # 2. Supabase
    if supabase is not None:
        try:
            res = supabase.table("entrega_history").select("*").order("id", desc=True).execute()
            for r in (res.data or []):
                clave = (str(r.get("fecha", "")), str(r.get("centro", "")), str(r.get("usuario", "")), str(r.get("url_documento", "")))
                if clave not in claves_vistas:
                    claves_vistas.add(clave)
                    registros_combinados.append(r)
        except Exception:
            pass

    # 3. Datos demo opcionales para presentación gerencial
    if incluir_demo:
        for r in obtener_datos_demo_entregas():
            registros_combinados.append(r)

    return registros_combinados

def parsear_lista_campo(valor):
    """Normaliza campos de lista que pueden venir como list, string separado por comas o None."""
    if valor is None:
        return []
    if isinstance(valor, list):
        return [str(x).strip() for x in valor if str(x).strip() and "ningun" not in str(x).lower()]
    texto = str(valor).strip()
    if not texto or "ningun" in texto.lower():
        return []
    return [x.strip() for x in texto.split(",") if x.strip() and "ningun" not in x.lower()]

def guardar_entrega_bd(datos_completos, datos_basicos):
    """Guarda en local persistente y en Supabase con fallback automático si faltan columnas nuevas."""
    st.session_state.local_entrega_history.append(datos_completos)
    guardar_estado_persistente()

    if supabase is None:
        return False, "Supabase inactivo (guardado en respaldo local)."

    try:
        supabase.table("entrega_history").insert(datos_completos).execute()
        return True, "Guardado completo en Supabase."
    except Exception:
        try:
            supabase.table("entrega_history").insert(datos_basicos).execute()
            return True, "Guardado en Supabase (esquema estándar) + detalle completo en plataforma."
        except Exception as db_err:
            return False, f"Error BD: {db_err}"

def calcular_alertas_criticas(registros):
    """Analiza todas las entregas y el estado de los centros para construir el listado de alertas críticas."""
    alertas = []
    hoy = obtener_hora_chile().date()

    # A. Alerta automática: Piloto no ha enviado Entrega de Turno el último día de faena
    for centro, fecha_fin in st.session_state.db_centros_fin_faena.items():
        if isinstance(fecha_fin, str):
            try:
                fecha_fin = datetime.date.fromisoformat(fecha_fin)
            except Exception:
                continue
        if hoy >= fecha_fin:
            entregas_centro = [r for r in registros if r.get("centro") == centro]
            entrego_en_ventana = False
            for r in entregas_centro:
                try:
                    f_reg = datetime.date.fromisoformat(str(r.get("fecha", ""))[:10])
                    if f_reg >= (fecha_fin - datetime.timedelta(days=1)):
                        entrego_en_ventana = True
                        break
                except Exception:
                    continue
            if not entrego_en_ventana:
                dias_atraso = (hoy - fecha_fin).days
                pilotos_c = [u for u, inf in st.session_state.db_usuarios.items() if inf.get("centro") == centro and inf.get("rol") != "admin"]
                responsable = ", ".join(pilotos_c) if pilotos_c else "Piloto de turno"
                detalle_atraso = "HOY es el último día de faena y aún no registra envío." if dias_atraso == 0 else f"Lleva {dias_atraso} día(s) de atraso desde el último día de faena ({fecha_fin.strftime('%d-%m-%Y')})."
                alertas.append({
                    "severidad": "CRÍTICA",
                    "categoria": "Entrega de Turno Pendiente",
                    "centro": centro,
                    "area": st.session_state.db_centros_areas.get(centro, "N/A"),
                    "fecha": str(fecha_fin),
                    "piloto": responsable,
                    "detalle": detalle_atraso,
                })

    # B. Alerta automática: Rotación ROV vencida (>= 7 días) por centro
    for centro, info_rov in st.session_state.db_rovs_por_centro.items():
        activo_id = info_rov.get("activo_id", 1)
        equipos = info_rov.get("equipos", {})
        eq = equipos.get(activo_id)
        if eq:
            f_ini = eq.get("fecha_inicio_uso", hoy)
            if isinstance(f_ini, str):
                try:
                    f_ini = datetime.date.fromisoformat(f_ini)
                except Exception:
                    f_ini = hoy
            dias_uso = (hoy - f_ini).days
            if dias_uso >= DIAS_ROTACION_ROV:
                alertas.append({
                    "severidad": "ALTA",
                    "categoria": "Rotación ROV Vencida (7+ días)",
                    "centro": centro,
                    "area": st.session_state.db_centros_areas.get(centro, "N/A"),
                    "fecha": str(hoy),
                    "piloto": "Turno actual",
                    "detalle": f"{eq.get('nombre', 'ROV')} (S/N: {eq.get('serie_rov', 'N/A')}) lleva {dias_uso} días continuos en uso. Corresponde rotar equipo.",
                })

    # C. Alertas derivadas de las Entregas de Turno
    for r in registros:
        centro = val_seguro(r, "centro", "Desconocido")
        area = val_seguro(r, "area", st.session_state.db_centros_areas.get(centro, "N/A"))
        fecha = val_seguro(r, "fecha", "Sin fecha")
        piloto = val_seguro(r, "usuario", "N/A")
        rov_txt = val_seguro(r, "rov_en_uso", "ROV en uso")

        # Falla específica reportada en cualquier ROV (En Uso o Stand-by)
        rov_falla = val_seguro(r, "rov_con_falla", "")
        if rov_falla and rov_falla.lower() not in ("sin fallas", "ninguno", "n/a"):
            comp_f = val_seguro(r, "componente_falla", "Equipo ROV")
            sev_f_raw = val_seguro(r, "severidad_falla", "Requiere cambio")
            det_f = val_seguro(r, "detalle_falla", "Sin detalle adicional.")
            sev_nivel = "CRÍTICA" if ("requiere" in sev_f_raw.lower() or "fuera" in sev_f_raw.lower()) else "ALTA"
            alertas.append({
                "severidad": sev_nivel,
                "categoria": f"Falla Específica ROV ({comp_f})",
                "centro": centro,
                "area": area,
                "fecha": fecha,
                "piloto": piloto,
                "detalle": f"Equipo afectado: {rov_falla} | Estado: {sev_f_raw} | Detalle: {det_f}",
            })

        est_rov = val_seguro(r, "estado_rov", "")
        if est_rov in ["Requiere cambio", "Regular"]:
            alertas.append({
                "severidad": "CRÍTICA" if est_rov == "Requiere cambio" else "MEDIA",
                "categoria": "ROV Dañado / Falla",
                "centro": centro,
                "area": area,
                "fecha": fecha,
                "piloto": piloto,
                "detalle": f"{rov_txt} reportado en estado '{est_rov}'.",
            })

        est_umb = val_seguro(r, "estado_umbilical", "")
        if est_umb in ["Requiere cambio", "Regular"]:
            alertas.append({
                "severidad": "CRÍTICA" if est_umb == "Requiere cambio" else "MEDIA",
                "categoria": "Cable Umbilical Dañado",
                "centro": centro,
                "area": area,
                "fecha": fecha,
                "piloto": piloto,
                "detalle": f"Cable umbilical ({rov_txt}) reportado en estado '{est_umb}'.",
            })

        est_ctrl = val_seguro(r, "estado_controlador", "")
        if est_ctrl in ["Requiere cambio", "Regular"]:
            alertas.append({
                "severidad": "CRÍTICA" if est_ctrl == "Requiere cambio" else "MEDIA",
                "categoria": "Controlador Dañado",
                "centro": centro,
                "area": area,
                "fecha": fecha,
                "piloto": piloto,
                "detalle": f"Controlador ({rov_txt}) reportado en estado '{est_ctrl}'.",
            })

        est_eqp = val_seguro(r, "estado_equipamiento", "")
        if est_eqp == "Requiere cambio":
            alertas.append({
                "severidad": "ALTA",
                "categoria": "Infraestructura / Equipamiento",
                "centro": centro,
                "area": area,
                "fecha": fecha,
                "piloto": piloto,
                "detalle": "Equipamiento de terreno (carpa/caseta/silla/lona) requiere cambio.",
            })

        mat_falt = parsear_lista_campo(r.get("materiales_faltantes"))
        herr_falt = parsear_lista_campo(r.get("herramientas_faltantes"))
        if mat_falt or herr_falt:
            partes = []
            if mat_falt:
                partes.append(f"Insumos ({len(mat_falt)}): {', '.join(mat_falt[:4])}" + ("..." if len(mat_falt) > 4 else ""))
            if herr_falt:
                partes.append(f"Herramientas ({len(herr_falt)}): {', '.join(herr_falt[:4])}" + ("..." if len(herr_falt) > 4 else ""))
            alertas.append({
                "severidad": "ALTA" if (len(mat_falt) + len(herr_falt)) >= 3 else "MEDIA",
                "categoria": "Falta de Insumos / Herramientas",
                "centro": centro,
                "area": area,
                "fecha": fecha,
                "piloto": piloto,
                "detalle": " | ".join(partes),
            })

        alerta_txt = val_seguro(r, "alertas_centro", "")
        if alerta_txt and alerta_txt.lower() not in ["ninguna", "sin novedades", "n/a", "no"]:
            alertas.append({
                "severidad": "ALTA",
                "categoria": "Alerta Declarada por Centro",
                "centro": centro,
                "area": area,
                "fecha": fecha,
                "piloto": piloto,
                "detalle": alerta_txt,
            })

    orden_sev = {"CRÍTICA": 0, "ALTA": 1, "MEDIA": 2}
    alertas.sort(key=lambda x: (orden_sev.get(x["severidad"], 3), x["fecha"]), reverse=False)
    return alertas

# ==============================================================================
# 4. GENERADORES DE PDF (INFORME CONSOLIDADO Y ENTREGA DE TURNO)
# ==============================================================================
def generar_pdf_consolidado(datos, anomalias, logo_filename, rov_cover, nombre_archivo):
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)

    # PÁGINA 1: PORTADA
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.set_text_color(15, 55, 105)
    pdf.cell(60, 10, "TECHTRIDENT", border=0, align="L")
    pdf.cell(70, 10, limpiar_texto_pdf("ÁREA ROBÓTICA"), border=0, align="C")
    pdf.set_text_color(0, 102, 204)
    cliente_str = limpiar_texto_pdf(str(datos.get("cliente", "CLIENTE")).upper())
    pdf.cell(60, 10, cliente_str[:20], border=0, align="R", ln=True)
    pdf.line(10, 22, 200, 22)
    pdf.ln(10)

    if rov_cover and os.path.exists(rov_cover):
        try:
            pdf.image(rov_cover, x=25, y=30, w=160)
            pdf.set_y(120)
        except Exception:
            pdf.set_y(60)
    else:
        pdf.set_y(60)

    pdf.set_font("Arial", "B", 24)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 10, "INFORME DIARIO", border=0, ln=True, align="C")
    pdf.set_font("Arial", "B", 18)
    pdf.cell(0, 10, limpiar_texto_pdf("INSPECCIÓN ROBÓTICA SUBMARINA"), border=0, ln=True, align="C")
    centro_str = limpiar_texto_pdf(str(datos.get("centro", "CENTRO")).upper())
    pdf.cell(0, 10, f"CENTRO {centro_str}", border=0, ln=True, align="C")
    pdf.ln(10)

    pdf.set_left_margin(25)
    pdf.set_right_margin(25)
    pdf.set_x(25)

    def add_cover_row(label, value):
        pdf.set_font("Arial", "B", 10)
        pdf.set_fill_color(240, 240, 240)
        pdf.cell(70, 8, limpiar_texto_pdf(f" {label}"), border=1, fill=True)
        pdf.set_font("Arial", "", 10)
        pdf.cell(90, 8, limpiar_texto_pdf(f" {str(value)[:45]}"), border=1, ln=True)

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
    pdf.set_font("Arial", "B", 8)
    pdf.set_text_color(15, 55, 105)
    pdf.cell(0, 5, limpiar_texto_pdf("TECHTRIDENT ÁREA ROBÓTICA - CONTACTO@TECHTRIDENT.CL"), align="C", ln=True)

    # PÁGINA 2: PLANIMETRÍA Y ACTIVIDADES
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 10, limpiar_texto_pdf("ESPECIFICACIÓN DEL CENTRO E INSPECCIÓN"), border=0, ln=True, align="C")
    pdf.ln(5)
    pdf.set_font("Arial", "B", 11)
    pdf.cell(0, 6, "ACTIVIDADES REALIZADAS:", ln=True)
    pdf.set_font("Arial", "", 10)
    act_am = limpiar_texto_pdf(datos.get("actividad_am", ""))
    act_pm = limpiar_texto_pdf(datos.get("actividad_pm", ""))
    obs = limpiar_texto_pdf(datos.get("observaciones", ""))
    pdf.multi_cell(0, 5, f"AM: {act_am}")
    pdf.multi_cell(0, 5, f"PM: {act_pm}")
    pdf.ln(3)
    pdf.multi_cell(0, 5, f"Observaciones de la jornada: {obs}")
    pdf.ln(10)

    if datos.get("planimetria"):
        try:
            temp_path = f"temp_pl_{uuid.uuid4().hex[:6]}.jpg"
            bytes_opt = optimizar_imagen_ram(datos["planimetria"], max_dim=1200)
            with open(temp_path, "wb") as f:
                f.write(bytes_opt)
            with Image.open(temp_path) as pil_img:
                w, h = pil_img.size
                aspect = h / w
                w_mm = 170
                h_mm = w_mm * aspect
                if h_mm > 160:
                    h_mm = 160
                    w_mm = h_mm / aspect
            pdf.image(temp_path, x=(210 - w_mm) / 2, y=pdf.get_y(), w=w_mm, h=h_mm)
            pdf.set_y(pdf.get_y() + h_mm + 10)
            os.remove(temp_path)
        except Exception:
            pdf.set_font("Arial", "I", 10)
            pdf.cell(0, 10, limpiar_texto_pdf("(No se adjuntó esquema válido o no se pudo procesar)"), ln=True, align="C")

    # PÁGINAS 3+: GRILLA DE FOTOGRAFÍAS
    if anomalias:
        anomalias_por_jaula = {}
        for a in anomalias:
            j = a.get("jaula", "N/A")
            anomalias_por_jaula.setdefault(j, []).append(a)

        for jaula, lista_anomalias in anomalias_por_jaula.items():
            pdf.add_page()
            pdf.set_font("Arial", "B", 16)
            pdf.cell(0, 10, limpiar_texto_pdf(f"IMÁGENES DE INSPECCIÓN JAULA {jaula}"), border=0, ln=True, align="C")
            pdf.ln(5)
            col_width = 85
            x_start = 15

            for anomalia in lista_anomalias:
                if pdf.get_y() > 220:
                    pdf.add_page()
                    pdf.set_font("Arial", "B", 16)
                    pdf.cell(0, 10, limpiar_texto_pdf(f"IMÁGENES DE INSPECCIÓN JAULA {jaula} (Cont.)"), border=0, ln=True, align="C")
                    pdf.ln(5)
                y_base = pdf.get_y()

                def draw_photo_card(foto_data, x_pos, is_reparada=False):
                    pdf.set_xy(x_pos, y_base)
                    pdf.set_draw_color(200, 200, 200)
                    pdf.rect(x_pos, y_base, col_width, 65)
                    if foto_data:
                        try:
                            temp = f"t_foto_{uuid.uuid4().hex[:6]}.jpg"
                            with open(temp, "wb") as f:
                                f.write(optimizar_imagen_ram(foto_data, 600))
                            with Image.open(temp) as img:
                                asp = img.height / img.width
                                w = col_width - 4
                                h = w * asp
                                if h > 45:
                                    h = 45
                                    w = h / asp
                            pdf.image(temp, x=x_pos + 2 + (col_width - 4 - w) / 2, y=y_base + 2, w=w, h=h)
                            os.remove(temp)
                        except Exception:
                            pass
                    pdf.set_xy(x_pos + 2, y_base + 48)
                    pdf.set_font("Arial", "", 8)
                    pdf.set_text_color(0, 0, 0)
                    desc = anomalia.get("descripcion", "")
                    red = anomalia.get("tipo_red", "")
                    ubic = anomalia.get("ubicacion", "")
                    prof = anomalia.get("profundidad", "")
                    texto_desc = limpiar_texto_pdf(f"{desc} Red {red} {jaula}\n{ubic} {prof} metros.")
                    pdf.multi_cell(col_width - 4, 4, texto_desc, align="C")
                    estado = str(anomalia.get("estado", "")).upper()
                    if is_reparada or estado == "REPARADA":
                        pdf.set_text_color(0, 128, 0)
                    else:
                        pdf.set_text_color(200, 0, 0)
                    pdf.set_font("Arial", "B", 9)
                    pdf.set_xy(x_pos, y_base + 58)
                    pdf.cell(col_width, 5, limpiar_texto_pdf(estado), align="C")
                    pdf.set_text_color(0, 0, 0)

                draw_photo_card(anomalia.get("foto_rotura"), x_start)
                draw_photo_card(anomalia.get("foto_reparacion"), x_start + col_width + 10, is_reparada=True)
                pdf.set_y(y_base + 70)

    # PÁGINA FINAL: MATRIZ DE RESULTADOS (Landscape)
    pdf.add_page(orientation="L")
    pdf.set_font("Arial", "B", 16)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 10, limpiar_texto_pdf("RESULTADOS DE LA INSPECCIÓN"), border=0, ln=True, align="L")
    pdf.ln(2)
    try:
        fecha_obj = datos.get("fecha")
        if isinstance(fecha_obj, str):
            fecha_obj = datetime.datetime.strptime(fecha_obj, "%Y-%m-%d").date()
        semana = fecha_obj.isocalendar()[1]
    except Exception:
        semana = ""

    cols = [
        ("N°", 8), ("Fecha", 22), ("Semana", 18), ("Jaula", 15), ("Centro", 30),
        ("Tipo Red", 20), ("Anomalia / Hallazgo", 60), ("Ubicación", 30),
        ("Profundidad", 25), ("Estado", 22), ("Servicio", 25)
    ]
    pdf.set_font("Arial", "B", 9)
    pdf.set_fill_color(220, 220, 220)
    pdf.set_text_color(0, 0, 0)
    for col_name, width in cols:
        pdf.cell(width, 8, limpiar_texto_pdf(col_name), border=1, fill=True, align="C")
    pdf.ln()

    pdf.set_font("Arial", "", 8)
    for i, a in enumerate(anomalias):
        estado = str(a.get("estado", ""))
        desc_safe = limpiar_texto_pdf(str(a.get("descripcion", "")).replace("\n", " ")[:40])
        centro_safe = limpiar_texto_pdf(str(datos.get("centro", ""))[:15])
        ubic_safe = limpiar_texto_pdf(str(a.get("ubicacion", ""))[:15])
        pdf.cell(cols[0][1], 8, str(i + 1), border=1, align="C")
        pdf.cell(cols[1][1], 8, str(datos.get("fecha", "")), border=1, align="C")
        pdf.cell(cols[2][1], 8, str(semana), border=1, align="C")
        pdf.cell(cols[3][1], 8, limpiar_texto_pdf(str(a.get("jaula", ""))[:8]), border=1, align="C")
        pdf.cell(cols[4][1], 8, centro_safe, border=1, align="C")
        pdf.cell(cols[5][1], 8, limpiar_texto_pdf(str(a.get("tipo_red", ""))[:10]), border=1, align="C")
        pdf.cell(cols[6][1], 8, desc_safe, border=1)
        pdf.cell(cols[7][1], 8, ubic_safe, border=1, align="C")
        pdf.cell(cols[8][1], 8, f"{a.get('profundidad', '')}m", border=1, align="C")
        if estado.lower() == "reparada":
            pdf.set_text_color(0, 128, 0)
        else:
            pdf.set_text_color(200, 0, 0)
        pdf.cell(cols[9][1], 8, limpiar_texto_pdf(estado), border=1, align="C")
        pdf.set_text_color(0, 0, 0)
        pdf.cell(cols[10][1], 8, limpiar_texto_pdf("Inspección"), border=1, align="C")
        pdf.ln()

    if datos.get("observaciones"):
        pdf.ln(5)
        pdf.set_font("Arial", "B", 10)
        pdf.cell(0, 6, "Observaciones Generales:", ln=True)
        pdf.set_font("Arial", "", 9)
        pdf.multi_cell(0, 5, limpiar_texto_pdf(f"* {datos.get('observaciones')}"))

    pdf.output(nombre_archivo)
    return nombre_archivo


def generar_pdf_entrega(datos, logo_filename, nombre_archivo, firma_path=None, diccionario_fotos=None, folio="", correlativo=""):
    pdf = FPDF()
    pdf.set_margins(10, 10, 10)
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()
    pdf.set_draw_color(180, 180, 180)

    if logo_filename and os.path.exists(logo_filename):
        try:
            pdf.image(logo_filename, x=10, y=8, h=20)
        except Exception:
            pass

    pdf.set_y(32)
    pdf.set_font("Arial", "B", 14)
    pdf.set_fill_color(15, 55, 105)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 10, "REPORTE FORMAL DE ENTREGA DE TURNO - ROV", border=0, ln=True, align="C", fill=True)

    hora_chile = obtener_hora_chile()
    fecha_hora_actual = hora_chile.strftime("%Y-%m-%d %H:%M:%S")
    d1 = datos.get("1. Información General", {})
    piloto_saliente = d1.get("Piloto_Saliente", "Desconocido")
    pdf.set_font("Arial", "I", 9)
    pdf.set_text_color(128, 128, 128)
    pdf.cell(
        0, 8,
        limpiar_texto_pdf(f"Folio: {folio} | Sello de Auditoría Inmutable: Generado el {fecha_hora_actual} por {piloto_saliente}"),
        border=0, ln=True, align="C"
    )
    pdf.set_font("Arial", "B", 12)
    pdf.set_text_color(15, 55, 105)
    pdf.cell(0, 6, limpiar_texto_pdf(f"N° {correlativo}"), border=0, ln=True, align="C")
    pdf.ln(5)

    h_cell = 8

    def print_section_header(title):
        pdf.set_fill_color(15, 55, 105)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Arial", "B", 10)
        pdf.cell(190, 8, limpiar_texto_pdf(f"  {title}"), border=0, ln=True, fill=True)
        pdf.ln(2)
        pdf.set_text_color(0, 0, 0)

    def print_row_2(l1, v1, l2, v2):
        pdf.set_font("Arial", "B", 9)
        pdf.cell(35, h_cell, limpiar_texto_pdf(l1), border=1)
        pdf.set_font("Arial", "", 9)
        pdf.cell(60, h_cell, limpiar_texto_pdf(str(v1)[:35]), border=1)
        pdf.set_font("Arial", "B", 9)
        pdf.cell(35, h_cell, limpiar_texto_pdf(l2), border=1)
        pdf.set_font("Arial", "", 9)
        pdf.cell(60, h_cell, limpiar_texto_pdf(str(v2)[:35]), border=1, ln=True)

    def print_multiline(label, text):
        pdf.set_fill_color(240, 240, 240)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Arial", "B", 9)
        pdf.cell(190, 8, limpiar_texto_pdf(f" {label}:"), border=1, ln=True, fill=True)
        pdf.set_font("Arial", "", 9)
        text_safe = limpiar_texto_pdf(str(text).strip()) if str(text).strip() else "Sin registro o sin novedades."
        x_s = pdf.get_x()
        y_s = pdf.get_y()
        pdf.multi_cell(190, 6, txt=f" {text_safe}", border=0)
        y_e = pdf.get_y()
        h_r = max(y_e - y_s, 8)
        pdf.set_xy(x_s, y_s)
        pdf.cell(190, h_r, "", border=1, ln=True)
        pdf.set_xy(x_s, y_s + h_r)

    def print_list(label, lst):
        pdf.set_fill_color(240, 240, 240)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Arial", "B", 9)
        pdf.cell(190, 8, limpiar_texto_pdf(f" {label}:"), border=1, ln=True, fill=True)
        pdf.set_font("Arial", "", 9)
        if not lst or (len(lst) == 1 and "ningun" in str(lst[0]).lower()):
            pdf.cell(190, 8, " - Sin registros asignados.", border=1, ln=True)
        else:
            for i in range(0, len(lst), 2):
                i1 = limpiar_texto_pdf(f" - {lst[i]}")
                i2 = limpiar_texto_pdf(f" - {lst[i + 1]}") if i + 1 < len(lst) else ""
                b_str = "LB" if i + 2 >= len(lst) else "L"
                b_str2 = "RB" if i + 2 >= len(lst) else "R"
                pdf.cell(95, 8, i1, border=b_str, ln=0)
                pdf.cell(95, 8, i2, border=b_str2, ln=1)

    print_section_header("1. INFORMACION GENERAL")
    print_row_2("Piloto Entrante:", d1.get("Piloto_Entrante", ""), "Piloto Saliente:", d1.get("Piloto_Saliente", ""))
    print_row_2("Fecha:", d1.get("Fecha", ""), "Centro:", d1.get("Centro", ""))
    pdf.set_font("Arial", "B", 9)
    pdf.cell(35, h_cell, "Area Asignada:", border=1)
    pdf.set_font("Arial", "", 9)
    pdf.cell(155, h_cell, limpiar_texto_pdf(str(d1.get("Área", ""))[:80]), border=1, ln=True)
    pdf.ln(4)

    d2 = datos.get("2. Estado de los Equipos (ROV)", {})
    if pdf.get_y() > 235:
        pdf.add_page()
    print_section_header("2. ESTADO DE LOS EQUIPOS (ROV)")
    pdf.set_font("Arial", "B", 9)
    pdf.cell(35, h_cell, "ROV En Uso:", border=1)
    pdf.set_font("Arial", "", 9)
    pdf.cell(155, h_cell, limpiar_texto_pdf(str(d2.get("ROV_En_Uso", ""))), border=1, ln=True)
    pdf.set_font("Arial", "B", 9)
    pdf.cell(35, h_cell, "ROV Stand-by:", border=1)
    pdf.set_font("Arial", "", 9)
    pdf.cell(155, h_cell, limpiar_texto_pdf(str(d2.get("ROV_Stand_by", ""))), border=1, ln=True)
    print_row_2("Estado ROV (Uso):", d2.get("Estado_General_ROV", ""), "Controlador:", d2.get("Estado_Controlador", ""))
    pdf.set_font("Arial", "B", 9)
    pdf.cell(35, h_cell, "Cable Umbilical:", border=1)
    pdf.set_font("Arial", "", 9)
    pdf.cell(155, h_cell, limpiar_texto_pdf(str(d2.get("Cable_Umbilical", ""))), border=1, ln=True)
    if d2.get("ROV_Con_Falla") and str(d2.get("ROV_Con_Falla")).lower() not in ("", "sin fallas", "none"):
        pdf.set_fill_color(254, 226, 226)
        pdf.set_text_color(153, 27, 27)
        pdf.set_font("Arial", "B", 9)
        pdf.cell(190, h_cell, limpiar_texto_pdf(f" REPORTE ESPECIFICO DE FALLA: {d2.get('ROV_Con_Falla')}"), border=1, ln=True, fill=True)
        pdf.set_text_color(0, 0, 0)
        print_row_2("Componente:", d2.get("Componente_Falla", ""), "Severidad:", d2.get("Severidad_Falla", ""))
        print_multiline("Detalle Tecnico de la Falla", d2.get("Detalle_Falla", ""))
    print_multiline("Observaciones de Equipos", d2.get("Observaciones_Equipos", ""))
    pdf.ln(4)

    d3 = datos.get("3. Terreno", {})
    if pdf.get_y() > 240:
        pdf.add_page()
    print_section_header("3. INFRAESTRUCTURA DE TERRENO")
    pdf.set_font("Arial", "B", 9)
    pdf.cell(45, h_cell, "Equipamiento Presente:", border=1)
    pdf.set_font("Arial", "", 9)
    pdf.cell(145, h_cell, limpiar_texto_pdf(str(d3.get("Equipamiento_Presente", ""))[:100]), border=1, ln=True)
    pdf.set_font("Arial", "B", 9)
    pdf.cell(45, h_cell, "Estado General:", border=1)
    pdf.set_font("Arial", "", 9)
    pdf.cell(145, h_cell, limpiar_texto_pdf(str(d3.get("Estado_del_Equipamiento", ""))[:100]), border=1, ln=True)
    print_multiline("Observaciones de Infraestructura", d3.get("Observaciones_Equipamiento", ""))
    pdf.ln(4)

    d4 = datos.get("4. Herramientas", {})
    d5 = datos.get("5. Materiales de Mantención", {})
    if pdf.get_y() > 220:
        pdf.add_page()
    print_section_header("4. INVENTARIO DE MANTENCION")
    print_list("Herramientas Presentes", d4.get("Herramientas_Presentes", []))
    print_list("Herramientas Faltantes (Reportadas)", d4.get("Herramientas_Faltantes", []))
    print_list("Materiales/Insumos Presentes", d5.get("Materiales_Presentes", []))
    print_list("Materiales/Insumos Faltantes", d5.get("Materiales_Faltantes", []))
    pdf.ln(4)

    d6 = datos.get("6. Operativa de Turno (14 días)", {})
    if pdf.get_y() > 200:
        pdf.add_page()
    print_section_header("5. RESUMEN OPERATIVO DEL TURNO (14 DIAS)")
    print_multiline("Faena Principal Realizada", d6.get("Faena_Realizada", ""))
    print_multiline("Alertas del Centro de Cultivo", d6.get("Alertas_del_Centro", ""))
    print_multiline("Tareas Pendientes (Para Piloto Entrante)", d6.get("Tareas_Pendientes", ""))
    print_multiline("Observaciones Generales", d6.get("Observaciones_Generales", ""))
    pdf.ln(8)

    if pdf.get_y() > 220:
        pdf.add_page()
    pdf.set_fill_color(15, 55, 105)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Arial", "B", 10)
    pdf.cell(190, 8, "  6. FIRMAS DE RESPONSABILIDAD", border=0, ln=True, fill=True)
    pdf.ln(2)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(190, 25, "", border=1, ln=True)
    if firma_path and os.path.exists(firma_path):
        pdf.image(firma_path, x=85, y=pdf.get_y() - 22, w=40, h=18)
    pdf.set_font("Arial", "B", 9)
    pdf.cell(190, 8, limpiar_texto_pdf(f"Firma Piloto ROV Saliente: {piloto_saliente}"), border=1, align="C", ln=True)

    if diccionario_fotos:
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_fill_color(15, 55, 105)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(190, 8, "  EVIDENCIA FOTOGRAFICA ROVs", border=0, ln=True, fill=True)
        pdf.ln(5)
        pdf.set_text_color(0, 0, 0)
        col_img = 0
        row_y = pdf.get_y()
        max_h_row = 0
        for titulo, img_file in diccionario_fotos.items():
            temp_path = f"temp_{uuid.uuid4().hex[:6]}.jpg"
            bytes_optimizados = optimizar_imagen_ram(img_file.getvalue())
            with open(temp_path, "wb") as f:
                f.write(bytes_optimizados)
            with Image.open(temp_path) as pil_img:
                w_px, h_px = pil_img.size
                aspect = h_px / w_px
                if aspect > (80 / 85):
                    h_mm = 75
                    w_mm = 75 / aspect
                else:
                    w_mm = 85
                    h_mm = 85 * aspect
            if col_img == 2:
                col_img = 0
                row_y += max_h_row + 15
                max_h_row = 0
            if row_y + 90 > 280:
                pdf.add_page()
                row_y = pdf.get_y()
                col_img = 0
                max_h_row = 0
            x_pos = 15 if col_img == 0 else 110
            pdf.set_xy(x_pos, row_y)
            pdf.set_font("Arial", "B", 8)
            pdf.cell(w_mm, 5, limpiar_texto_pdf(titulo), border=0, align="C", ln=2)
            y_foto = pdf.get_y()
            pdf.rect(x_pos - 1, y_foto - 1, w_mm + 2, h_mm + 2)
            pdf.image(temp_path, x=x_pos, y=y_foto, w=w_mm, h=h_mm)
            max_h_row = max(max_h_row, h_mm + 5)
            col_img += 1
            os.remove(temp_path)
        pdf.set_y(row_y + max_h_row + 10)

    pdf.set_auto_page_break(auto=False)
    pdf.set_y(-18)
    pdf.set_font("Arial", "B", 8)
    pdf.set_text_color(15, 55, 105)
    pdf.cell(190, 4, "TECHTRIDENT - NTORRES@TECHTRIDENT.CL - WWW.TECHTRIDENT.CL", border=0, align="C", ln=1)
    pdf.set_font("Arial", "I", 8)
    pdf.set_text_color(128, 128, 128)
    pdf.cell(190, 4, limpiar_texto_pdf("TechTrident 2026 ©"), border=0, align="C")

    pdf.output(nombre_archivo)
    return nombre_archivo

# ==============================================================================
# 5. COMPONENTES REUTILIZABLES (BARRA DE VISTAS, ALERTA 7 DÍAS, GESTIÓN ROV)
# ==============================================================================
def render_barra_superior_admin():
    """Permite al jefe alternar instantáneamente entre Gerencia, Vista Piloto y Suite Completa."""
    if not es_administrador():
        return
    with st.container(border=True):
        st.markdown(
            "<p style='margin:0 0 8px 0; font-weight:700; color:#38bdf8 !important;'>"
            "🧭 SELECTOR DE DEMOSTRACIÓN Y VISTAS (MODO GERENCIA)</p>",
            unsafe_allow_html=True
        )
        c_m1, c_m2, c_m3 = st.columns(3)
        with c_m1:
            tipo_g = "primary" if st.session_state.admin_view_mode == "gerencia" else "secondary"
            if st.button("👔 PANEL GERENCIAL (JEFE)", type=tipo_g, use_container_width=True, key="sw_gerencia"):
                st.session_state.admin_view_mode = "gerencia"
                set_page("main_menu")
                st.rerun()
        with c_m2:
            tipo_p = "primary" if st.session_state.admin_view_mode == "piloto_demo" else "secondary"
            if st.button("👷 VER COMO PILOTO (USUARIOS)", type=tipo_p, use_container_width=True, key="sw_piloto"):
                st.session_state.admin_view_mode = "piloto_demo"
                set_page("main_menu")
                st.rerun()
        with c_m3:
            tipo_s = "primary" if st.session_state.admin_view_mode == "suite_completa" else "secondary"
            if st.button("⚓ SUITE COMPLETA TECHTRIDENT", type=tipo_s, use_container_width=True, key="sw_suite"):
                st.session_state.admin_view_mode = "suite_completa"
                set_page("main_menu")
                st.rerun()


def render_alerta_rotacion_7_dias(centro_nombre):
    """Muestra alerta automática cada 7 días para rotar el ROV del centro."""
    info_rovs = asegurar_rovs_centro(centro_nombre)
    activo_id = info_rovs["activo_id"]
    equipos = info_rovs["equipos"]
    if activo_id not in equipos and equipos:
        activo_id = list(equipos.keys())[0]
        info_rovs["activo_id"] = activo_id

    eq_activo = equipos.get(activo_id)
    if not eq_activo:
        return

    hoy = obtener_hora_chile().date()
    f_ini = eq_activo.get("fecha_inicio_uso", hoy)
    if isinstance(f_ini, str):
        try:
            f_ini = datetime.date.fromisoformat(f_ini)
        except Exception:
            f_ini = hoy
    dias_uso = max((hoy - f_ini).days, 0)
    dias_restantes = max(DIAS_ROTACION_ROV - dias_uso, 0)
    otros_ids = [rid for rid in equipos.keys() if rid != activo_id]
    standby_id = otros_ids[0] if otros_ids else None
    eq_standby = equipos.get(standby_id) if standby_id else None

    if dias_uso >= DIAS_ROTACION_ROV:
        with st.container(border=True):
            st.error(
                f"🚨 **ALERTA DE ROTACIÓN OBLIGATORIA (CICLO 7 DÍAS) — {centro_nombre}**\n\n"
                f"El equipo **{eq_activo['nombre']}** (N° Serie: `{eq_activo['serie_rov']}`) lleva **{dias_uso} días en uso** "
                f"(desde el {f_ini.strftime('%d-%m-%Y')}). Corresponde rotar el equipo y realizar mantención preventiva."
            )
            if eq_standby:
                col_r1, col_r2 = st.columns(2)
                with col_r1:
                    if st.button(
                        f"🔄 ROTAR AHORA A {eq_standby['nombre']} (S/N: {eq_standby['serie_rov']})",
                        type="primary",
                        use_container_width=True,
                        key=f"btn_rotar_7d_{centro_nombre}"
                    ):
                        info_rovs["activo_id"] = standby_id
                        equipos[standby_id]["fecha_inicio_uso"] = hoy
                        st.session_state.historial_rotaciones.append({
                            "fecha": str(hoy),
                            "centro": centro_nombre,
                            "piloto": st.session_state.current_user,
                            "equipo_saliente": f"{eq_activo['nombre']} ({eq_activo['serie_rov']})",
                            "equipo_entrante": f"{eq_standby['nombre']} ({eq_standby['serie_rov']})",
                            "dias_uso_anterior": dias_uso,
                        })
                        guardar_estado_persistente()
                        st.success(f"✅ Rotación registrada: {eq_standby['nombre']} quedó EN USO. Recuerde realizar mantención a {eq_activo['nombre']}.")
                        time.sleep(1.5)
                        st.rerun()
                with col_r2:
                    st.info(f"📅 Equipo Stand-by listo: **{eq_standby['nombre']}** | Últ. mantención: **{eq_standby['mantencion']}**")
    else:
        with st.container(border=True):
            col_i1, col_i2 = st.columns([3, 1])
            with col_i1:
                st.info(
                    f"🟢 **Equipo en uso actual ({centro_nombre}):** {eq_activo['nombre']} (N° Serie: `{eq_activo['serie_rov']}`) "
                    f"| Día **{dias_uso} de {DIAS_ROTACION_ROV}** (Próxima rotación en **{dias_restantes} día(s)**)."
                )
            with col_i2:
                st.progress(min(dias_uso / float(DIAS_ROTACION_ROV), 1.0))


def render_gestion_rovs_piloto(centro_nombre):
    """Sección para que los pilotos gestionen series de ROV, fechas de mantenimiento y equipo en uso."""
    st.button("⬅️ Volver al Menú Principal", on_click=set_page, args=("main_menu",))
    st.markdown(f"<h1 style='text-align: center;'>⚙️ Gestión de Equipos ROV — {centro_nombre}</h1>", unsafe_allow_html=True)
    st.caption("Administre los números de serie de los ROVs del centro, actualice fechas de mantención y controle la rotación semanal (cada 7 días).")
    st.divider()

    render_alerta_rotacion_7_dias(centro_nombre)

    info_rovs = asegurar_rovs_centro(centro_nombre)
    equipos = info_rovs["equipos"]
    opciones_ids = list(equipos.keys())
    hoy = obtener_hora_chile().date()

    # Selector rápido de equipo en uso
    with st.container(border=True):
        st.subheader("🔄 Selección de Equipo en Uso Actual")
        idx_act = opciones_ids.index(info_rovs["activo_id"]) if info_rovs["activo_id"] in opciones_ids else 0
        col_sel1, col_sel2 = st.columns([2, 1])
        with col_sel1:
            nuevo_activo = st.selectbox(
                "Equipo actualmente operando en agua",
                opciones_ids,
                index=idx_act,
                format_func=lambda x: f"{equipos[x]['nombre']} — S/N ROV: {equipos[x]['serie_rov']}",
                key=f"sel_activo_gest_{centro_nombre}"
            )
        with col_sel2:
            f_ini_sel = equipos[nuevo_activo].get("fecha_inicio_uso", hoy)
            if isinstance(f_ini_sel, str):
                try:
                    f_ini_sel = datetime.date.fromisoformat(f_ini_sel)
                except Exception:
                    f_ini_sel = hoy
            nueva_fecha_inicio = st.date_input("Fecha inicio de uso", value=f_ini_sel, key=f"fini_gest_{centro_nombre}")

        if st.button("💾 Guardar Equipo en Uso y Fecha de Inicio", type="primary", use_container_width=True):
            anterior_id = info_rovs["activo_id"]
            info_rovs["activo_id"] = nuevo_activo
            equipos[nuevo_activo]["fecha_inicio_uso"] = nueva_fecha_inicio
            if anterior_id != nuevo_activo and anterior_id in equipos:
                st.session_state.historial_rotaciones.append({
                    "fecha": str(hoy),
                    "centro": centro_nombre,
                    "piloto": st.session_state.current_user,
                    "equipo_saliente": f"{equipos[anterior_id]['nombre']} ({equipos[anterior_id]['serie_rov']})",
                    "equipo_entrante": f"{equipos[nuevo_activo]['nombre']} ({equipos[nuevo_activo]['serie_rov']})",
                    "dias_uso_anterior": max((hoy - equipos[anterior_id].get("fecha_inicio_uso", hoy)).days, 0),
                })
            guardar_estado_persistente()
            st.success("✅ Estado de equipo en uso actualizado correctamente.")
            st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)
    st.subheader("📋 Fichas Técnicas de ROVs del Centro (Editar Series y Mantención)")

    cols = st.columns(max(len(opciones_ids), 1))
    for i, rid in enumerate(opciones_ids):
        eq = equipos[rid]
        es_activo = (rid == info_rovs["activo_id"])
        etiqueta = "🟢 EN USO" if es_activo else "🟡 STAND-BY"
        with cols[i % len(cols)]:
            with st.container(border=True):
                st.markdown(f"### {eq['nombre']} ({etiqueta})")
                with st.form(f"form_edit_rov_{centro_nombre}_{rid}"):
                    ed_nombre = st.text_input("Identificador", value=eq["nombre"])
                    ed_serie_rov = st.text_input("N° Serie ROV", value=eq["serie_rov"])
                    ed_serie_ctrl = st.text_input("N° Serie Controlador", value=eq["serie_ctrl"])
                    f_mant = eq.get("mantencion", hoy)
                    if isinstance(f_mant, str):
                        try:
                            f_mant = datetime.date.fromisoformat(f_mant)
                        except Exception:
                            f_mant = hoy
                    ed_mant = st.date_input("Fecha Última Mantención", value=f_mant)
                    if st.form_submit_button("💾 Actualizar Ficha ROV", use_container_width=True):
                        cambio_mant = (ed_mant != f_mant)
                        equipos[rid]["nombre"] = ed_nombre
                        equipos[rid]["serie_rov"] = ed_serie_rov
                        equipos[rid]["serie_ctrl"] = ed_serie_ctrl
                        equipos[rid]["mantencion"] = ed_mant
                        if cambio_mant:
                            st.session_state.historial_mantenciones.append({
                                "fecha_registro": str(hoy),
                                "centro": centro_nombre,
                                "piloto": st.session_state.current_user,
                                "equipo": f"{ed_nombre} (S/N: {ed_serie_rov})",
                                "fecha_mantencion_declarada": str(ed_mant),
                            })
                        guardar_estado_persistente()
                        st.success(f"✅ {ed_nombre} actualizado correctamente.")
                        st.rerun()

    with st.expander("➕ Agregar un ROV Adicional a este Centro", expanded=False):
        with st.form(f"form_add_rov_piloto_{centro_nombre}", clear_on_submit=True):
            c_a1, c_a2 = st.columns(2)
            with c_a1:
                n_nom = st.text_input("Nombre Equipo (Ej: ROV 3 - Backup)")
                n_ser = st.text_input("N° Serie ROV")
            with c_a2:
                n_ctrl = st.text_input("N° Serie Controlador")
                n_mant = st.date_input("Fecha Última Mantención", value=hoy)
            if st.form_submit_button("Registrar Nuevo ROV", use_container_width=True):
                if n_nom and n_ser:
                    nuevo_id = max(equipos.keys()) + 1 if equipos else 1
                    equipos[nuevo_id] = {
                        "nombre": n_nom,
                        "serie_rov": n_ser,
                        "serie_ctrl": n_ctrl or n_ser,
                        "mantencion": n_mant,
                        "fecha_inicio_uso": hoy,
                    }
                    guardar_estado_persistente()
                    st.success(f"✅ Equipo {n_nom} agregado al centro {centro_nombre}.")
                    st.rerun()
                else:
                    st.error("Debe ingresar al menos el Nombre y el N° de Serie del ROV.")


def render_historial_entregas_centro(centro_nombre):
    """Permite que ambos pilotos del centro revisen las entregas históricas de su centro."""
    st.button("⬅️ Volver al Menú Principal", on_click=set_page, args=("main_menu",))
    st.markdown(f"<h1 style='text-align: center;'>📚 Entregas de Turno Históricas — {centro_nombre}</h1>", unsafe_allow_html=True)
    st.info("Vista compartida para ambos pilotos del centro (piloto entrante y saliente). Revise el último traspaso, pendientes y descargue los PDFs.")
    st.divider()

    centros_disp = list(st.session_state.db_centros_areas.keys())
    if es_administrador():
        idx_c = centros_disp.index(centro_nombre) if centro_nombre in centros_disp else 0
        centro_consulta = st.selectbox("Centro consultado (Simulación Piloto)", centros_disp, index=idx_c)
    else:
        centro_consulta = centro_nombre

    todos = obtener_todas_las_entregas(incluir_demo=st.session_state.usar_datos_demo and es_administrador())
    del_centro = [r for r in todos if r.get("centro") == centro_consulta]

    if not del_centro:
        st.warning(f"Aún no se registran entregas de turno históricas para **{centro_consulta}**.")
        return

    df_c = limpiar_df_vista(pd.DataFrame(del_centro))
    cols_pref = ["fecha", "usuario", "piloto_entrante", "rov_en_uso", "rov_con_falla", "estado_rov", "estado_umbilical", "alertas_centro", "url_documento"]
    cols_ok = [c for c in cols_pref if c in df_c.columns]

    st.dataframe(
        df_c[cols_ok],
        column_config={"url_documento": st.column_config.LinkColumn("PDF Entrega", display_text="📥 Descargar PDF")},
        use_container_width=True
    )

    st.subheader("🔎 Detalle de Entregas del Centro (Traspaso entre Contraturnos)")
    for idx, reg in enumerate(del_centro[:10]):
        f_txt = val_seguro(reg, "fecha", "S/F")
        u_sal = val_seguro(reg, "usuario", "Sin registro")
        u_ent = val_seguro(reg, "piloto_entrante", "Sin registro")
        r_uso = val_seguro(reg, "rov_en_uso", "ROV")
        titulo_exp = f"📅 {f_txt} | Saliente: {u_sal} ➔ Entrante: {u_ent} | {r_uso}"
        with st.expander(titulo_exp, expanded=(idx == 0)):
            c1, c2, c3 = st.columns(3)
            c1.write(f"**Estado ROV (Uso):** {val_seguro(reg, 'estado_rov', 'No registrado')}")
            c2.write(f"**Controlador:** {val_seguro(reg, 'estado_controlador', 'No registrado')}")
            c3.write(f"**Cable Umbilical:** {val_seguro(reg, 'estado_umbilical', 'No registrado')}")
            r_falla = val_seguro(reg, "rov_con_falla", "")
            if r_falla:
                st.error(
                    f"🔧 **Falla reportada en {r_falla}** | Componente: {val_seguro(reg, 'componente_falla', 'ROV')} "
                    f"| Severidad: {val_seguro(reg, 'severidad_falla', 'Alerta')}\n\n"
                    f"Detalle: {val_seguro(reg, 'detalle_falla', 'Sin detalle')}"
                )
            faena_r = val_seguro(reg, "faena_realizada", "")
            if faena_r:
                st.write(f"**Faena Realizada:** {faena_r}")
            pend_r = val_seguro(reg, "tareas_pendientes", "")
            if pend_r:
                st.info(f"📌 **Tareas Pendientes para el turno entrante:** {pend_r}")
            alerta_r = val_seguro(reg, "alertas_centro", "")
            if alerta_r:
                st.warning(f"⚠️ **Alertas del Centro:** {alerta_r}")
            mat_f = parsear_lista_campo(reg.get("materiales_faltantes"))
            her_f = parsear_lista_campo(reg.get("herramientas_faltantes"))
            if mat_f or her_f:
                st.error(f"🧰 **Faltantes reportados:** Herramientas: {', '.join(her_f) if her_f else 'Ninguna'} | Insumos: {', '.join(mat_f) if mat_f else 'Ninguno'}")
            url_r = val_seguro(reg, "url_documento", "")
            if url_r.startswith("http"):
                st.link_button("📥 Abrir / Descargar PDF Original", url_r)


def render_panel_gerencial_completo():
    """Panel principal del Jefe de Operaciones: Alertas Críticas, Entregas por Centro, Gráficos y Administración."""
    st.markdown("<h1 style='text-align: center;'>👔 Panel Gerencial — Jefatura de Operaciones ROV</h1>", unsafe_allow_html=True)

    col_top_g1, col_top_g2 = st.columns([3, 1])
    with col_top_g1:
        st.write(f"Sesión Gerencial Activa: **{st.session_state.current_user}** | Control multi-centro de Entregas de Turno, Alertas Críticas y Flota ROV.")
    with col_top_g2:
        st.session_state.usar_datos_demo = st.toggle(
            "🧪 Datos demo (Presentación)",
            value=st.session_state.usar_datos_demo,
            help="Activa registros de ejemplo en los centros para visualizar alertas y gráficos en vivo."
        )

    registros = obtener_todas_las_entregas(incluir_demo=st.session_state.usar_datos_demo)
    alertas = calcular_alertas_criticas(registros)

    alertas_criticas = [a for a in alertas if a["severidad"] == "CRÍTICA"]
    centros_rov_problema = sorted(list(set(
        a["centro"] for a in alertas if (
            a["categoria"] in ["ROV Dañado / Falla", "Cable Umbilical Dañado", "Controlador Dañado"]
            or a["categoria"].startswith("Falla Específica ROV")
        )
    )))
    entregas_pendientes_fin = [a for a in alertas if a["categoria"] == "Entrega de Turno Pendiente"]

    with st.container(border=True):
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("📋 Entregas Registradas", len(registros))
        k2.metric("🚨 Alertas Críticas", len(alertas_criticas))
        k3.metric("🔧 Centros con ROV/Equipo con Fallas", len(centros_rov_problema))
        k4.metric("⏰ Entregas Pendientes (Fin Faena)", len(entregas_pendientes_fin))

    st.markdown("<br>", unsafe_allow_html=True)
    tab_alertas, tab_entregas, tab_graficos, tab_admin = st.tabs([
        f"🚨 Alertas Críticas ({len(alertas)})",
        "📂 Entregas por Centro",
        "📈 Gráficos de Fallas y Equipos",
        "⚙️ Gestión (Pilotos, Centros, Turnos y ROVs)"
    ])

    # ---- TAB 1: ALERTAS CRÍTICAS ----
    with tab_alertas:
        st.subheader("🚨 Monitor de Alertas Críticas de Operaciones")
        st.caption("Detecta automáticamente cables umbilicales dañados, ROVs con fallas, falta de insumos, alertas declaradas por centro, rotaciones vencidas y entregas no enviadas el último día de faena.")

        if entregas_pendientes_fin:
            for ep in entregas_pendientes_fin:
                st.error(
                    f"⏰ **ENTREGA DE TURNO NO ENVIADA (ÚLTIMO DÍA DE FAENA):** "
                    f"**{ep['centro']}** ({ep['area']}) | Responsable: **{ep['piloto']}** — {ep['detalle']}"
                )

        if not alertas:
            st.success("✅ Excelente: No existen alertas críticas activas en ningún centro.")
        else:
            df_al = pd.DataFrame(alertas)
            cf1, cf2, cf3 = st.columns(3)
            with cf1:
                f_sev = st.selectbox("Filtrar por Severidad", ["Todas", "CRÍTICA", "ALTA", "MEDIA"], key="al_sev")
            with cf2:
                f_cat = st.selectbox("Filtrar por Tipo de Alerta", ["Todas"] + sorted(df_al["categoria"].unique().tolist()), key="al_cat")
            with cf3:
                f_cen = st.selectbox("Filtrar por Centro", ["Todos"] + sorted(df_al["centro"].unique().tolist()), key="al_cen")

            df_al_f = df_al.copy()
            if f_sev != "Todas":
                df_al_f = df_al_f[df_al_f["severidad"] == f_sev]
            if f_cat != "Todas":
                df_al_f = df_al_f[df_al_f["categoria"] == f_cat]
            if f_cen != "Todos":
                df_al_f = df_al_f[df_al_f["centro"] == f_cen]

            for _, row in df_al_f.iterrows():
                msg = f"**[{row['severidad']}] {row['categoria']}** — **{row['centro']}** ({row['area']}) | Piloto: {row['piloto']} | Fecha: {row['fecha']}\n\n{row['detalle']}"
                if row["severidad"] == "CRÍTICA":
                    st.error(f"🔴 {msg}")
                elif row["severidad"] == "ALTA":
                    st.warning(f"🟠 {msg}")
                else:
                    st.info(f"🟡 {msg}")

            st.markdown("---")
            st.dataframe(df_al_f, use_container_width=True)

    # ---- TAB 2: ENTREGAS POR CENTRO ----
    with tab_entregas:
        st.subheader("📂 Revisión Gerencial de Entregas de Turno por Centro")
        if not registros:
            st.info("No hay entregas de turno registradas aún.")
        else:
            df_ent = pd.DataFrame(registros)
            if "fecha" in df_ent.columns:
                df_ent["fecha_dt"] = pd.to_datetime(df_ent["fecha"], errors="coerce")
                df_ent["Año"] = df_ent["fecha_dt"].dt.year.fillna(0).astype(int).astype(str).replace("0", "Desc.")
                df_ent["Mes"] = df_ent["fecha_dt"].dt.month.fillna(0).astype(int).astype(str).replace("0", "Desc.")
            else:
                df_ent["Año"] = "Desc."
                df_ent["Mes"] = "Desc."

            c_e1, c_e2, c_e3, c_e4 = st.columns(4)
            with c_e1:
                areas_u = ["Todas"] + sorted([str(x) for x in df_ent["area"].dropna().unique()]) if "area" in df_ent.columns else ["Todas"]
                sel_area = st.selectbox("Área", areas_u, key="ger_area")
            with c_e2:
                centros_u = ["Todos"] + sorted([str(x) for x in df_ent["centro"].dropna().unique()]) if "centro" in df_ent.columns else ["Todos"]
                sel_cen = st.selectbox("Centro de Cultivo", centros_u, key="ger_cen")
            with c_e3:
                pilotos_u = ["Todos"] + sorted([str(x) for x in df_ent["usuario"].dropna().unique()]) if "usuario" in df_ent.columns else ["Todos"]
                sel_pil = st.selectbox("Piloto Saliente", pilotos_u, key="ger_pil")
            with c_e4:
                meses_u = ["Todos"] + sorted(df_ent["Mes"].unique().tolist())
                sel_mes = st.selectbox("Mes", meses_u, key="ger_mes")

            df_f = df_ent.copy()
            if sel_area != "Todas" and "area" in df_f.columns:
                df_f = df_f[df_f["area"] == sel_area]
            if sel_cen != "Todos" and "centro" in df_f.columns:
                df_f = df_f[df_f["centro"] == sel_cen]
            if sel_pil != "Todos" and "usuario" in df_f.columns:
                df_f = df_f[df_f["usuario"] == sel_pil]
            if sel_mes != "Todos":
                df_f = df_f[df_f["Mes"] == sel_mes]

            cols_ver = [
                "fecha", "centro", "area", "usuario", "piloto_entrante",
                "rov_en_uso", "rov_con_falla", "componente_falla",
                "estado_rov", "estado_controlador", "estado_umbilical",
                "alertas_centro", "url_documento"
            ]
            cols_ver = [c for c in cols_ver if c in df_f.columns]
            st.dataframe(
                limpiar_df_vista(df_f[cols_ver]),
                column_config={"url_documento": st.column_config.LinkColumn("Enlace PDF", display_text="📥 Descargar PDF")},
                use_container_width=True
            )

            col_ex1, col_ex2 = st.columns(2)
            with col_ex1:
                csv_data = df_f.drop(columns=["fecha_dt"], errors="ignore").to_csv(index=False).encode("utf-8")
                st.download_button(
                    "📊 Exportar Entregas Filtradas a Excel (CSV)",
                    data=csv_data,
                    file_name=f"Entregas_Turno_{obtener_hora_chile().date()}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
            with col_ex2:
                if st.button("🗂️ Preparar ZIP con PDFs Filtrados", use_container_width=True, key="ger_zip_btn"):
                    with st.spinner("Descargando PDFs desde la nube y comprimiendo..."):
                        zip_buf = io.BytesIO()
                        cantidad_pdfs = 0
                        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                            for idx_z, r_z in df_f.iterrows():
                                url_z = r_z.get("url_documento")
                                if pd.notnull(url_z) and str(url_z).startswith("http"):
                                    try:
                                        req = urllib.request.Request(str(url_z), headers={"User-Agent": "Mozilla/5.0"})
                                        with urllib.request.urlopen(req, timeout=10) as resp:
                                            fname = f"Entrega_{r_z.get('centro', 'Centro')}_{r_z.get('fecha', 'Fecha')}_{idx_z}.pdf".replace("/", "-").replace(" ", "_")
                                            zf.writestr(fname, resp.read())
                                            cantidad_pdfs += 1
                                    except Exception:
                                        pass
                        if cantidad_pdfs > 0:
                            st.session_state["ger_zip_bytes"] = zip_buf.getvalue()
                        else:
                            st.warning("Los registros filtrados no tienen enlaces PDF en la nube disponibles para comprimir.")

                if "ger_zip_bytes" in st.session_state:
                    st.download_button(
                        "📥 Descargar Paquete ZIP",
                        data=st.session_state["ger_zip_bytes"],
                        file_name=f"Entregas_PDF_{obtener_hora_chile().date()}.zip",
                        mime="application/zip",
                        use_container_width=True
                    )

    # ---- TAB 3: GRÁFICOS DE FALLAS Y EQUIPOS ----
    with tab_graficos:
        st.subheader("📈 Inteligencia Operacional: Fallas Recurrentes y Estado de Flota ROV")
        if not registros:
            st.info("No hay suficientes datos para generar gráficos.")
        else:
            conteo_fallas_tipo = {
                "ROV Dañado / Regular": 0,
                "Cable Umbilical": 0,
                "Controlador": 0,
                "Equipamiento Terreno": 0,
                "Falta de Insumos": 0,
                "Falta de Herramientas": 0,
            }
            fallas_por_centro = {}
            rovs_con_problemas_lista = []

            for r in registros:
                cen = val_seguro(r, "centro", "Desconocido")
                area_r = val_seguro(r, "area", st.session_state.db_centros_areas.get(cen, "N/A"))
                rov_u = val_seguro(r, "rov_en_uso", "ROV")
                fecha_r = val_seguro(r, "fecha", "Sin fecha")
                obs_r = val_seguro(r, "alertas_centro", "Sin detalle")
                incidencias_reg = 0

                # Falla reportada explícitamente sobre un ROV específico (En Uso o Stand-by)
                rov_f_esp = val_seguro(r, "rov_con_falla", "")
                if rov_f_esp and rov_f_esp.lower() not in ("sin fallas", "ninguno", "n/a"):
                    comp_esp = val_seguro(r, "componente_falla", "ROV Principal")
                    sev_esp = val_seguro(r, "severidad_falla", "Requiere cambio")
                    det_esp = val_seguro(r, "detalle_falla", obs_r)
                    comp_low = comp_esp.lower()
                    if "umbilical" in comp_low:
                        conteo_fallas_tipo["Cable Umbilical"] += 1
                    elif "controlador" in comp_low:
                        conteo_fallas_tipo["Controlador"] += 1
                    else:
                        conteo_fallas_tipo["ROV Dañado / Regular"] += 1
                    incidencias_reg += 1
                    rovs_con_problemas_lista.append({
                        "Centro": cen, "Área": area_r, "Equipo con Falla": rov_f_esp,
                        "Componente": comp_esp, "Estado": sev_esp,
                        "Fecha": fecha_r, "Observación": det_esp
                    })

                est_r_v = val_seguro(r, "estado_rov", "")
                if est_r_v in ["Requiere cambio", "Regular"]:
                    conteo_fallas_tipo["ROV Dañado / Regular"] += 1
                    incidencias_reg += 1
                    rovs_con_problemas_lista.append({
                        "Centro": cen, "Área": area_r, "Equipo con Falla": rov_u,
                        "Componente": "ROV Principal", "Estado": est_r_v,
                        "Fecha": fecha_r, "Observación": obs_r
                    })
                est_u_v = val_seguro(r, "estado_umbilical", "")
                if est_u_v in ["Requiere cambio", "Regular"]:
                    conteo_fallas_tipo["Cable Umbilical"] += 1
                    incidencias_reg += 1
                    rovs_con_problemas_lista.append({
                        "Centro": cen, "Área": area_r, "Equipo con Falla": rov_u,
                        "Componente": "Cable Umbilical", "Estado": est_u_v,
                        "Fecha": fecha_r, "Observación": obs_r
                    })
                est_c_v = val_seguro(r, "estado_controlador", "")
                if est_c_v in ["Requiere cambio", "Regular"]:
                    conteo_fallas_tipo["Controlador"] += 1
                    incidencias_reg += 1
                    rovs_con_problemas_lista.append({
                        "Centro": cen, "Área": area_r, "Equipo con Falla": rov_u,
                        "Componente": "Controlador", "Estado": est_c_v,
                        "Fecha": fecha_r, "Observación": obs_r
                    })
                if val_seguro(r, "estado_equipamiento", "") in ["Requiere cambio", "Regular"]:
                    conteo_fallas_tipo["Equipamiento Terreno"] += 1
                    incidencias_reg += 1
                if parsear_lista_campo(r.get("materiales_faltantes")):
                    conteo_fallas_tipo["Falta de Insumos"] += 1
                    incidencias_reg += 1
                if parsear_lista_campo(r.get("herramientas_faltantes")):
                    conteo_fallas_tipo["Falta de Herramientas"] += 1
                    incidencias_reg += 1

                if incidencias_reg > 0:
                    fallas_por_centro[cen] = fallas_por_centro.get(cen, 0) + incidencias_reg

            cg1, cg2 = st.columns(2)
            with cg1:
                st.markdown("#### 🔧 Fallas Más Recurrentes")
                df_f_tipo = pd.DataFrame(
                    {"Tipo de Falla": list(conteo_fallas_tipo.keys()), "Cantidad": list(conteo_fallas_tipo.values())}
                ).sort_values("Cantidad", ascending=False).set_index("Tipo de Falla")
                st.bar_chart(df_f_tipo, color="#ff4b4b")

            with cg2:
                st.markdown("#### 🏭 Centros con Más Fallas de Equipos e Insumos")
                if fallas_por_centro:
                    df_f_cen = pd.DataFrame(
                        {"Centro": list(fallas_por_centro.keys()), "Total Fallas": list(fallas_por_centro.values())}
                    ).sort_values("Total Fallas", ascending=False).set_index("Centro")
                    st.bar_chart(df_f_cen, color="#f59e0b")
                else:
                    st.success("Sin fallas registradas por centro.")

            st.markdown("---")
            st.markdown("#### 🚨 Detalle: ¿En qué Centros hay ROV / Equipos con Problemas?")
            if rovs_con_problemas_lista:
                df_prob = pd.DataFrame(rovs_con_problemas_lista)
                st.dataframe(df_prob, use_container_width=True)
            else:
                st.success("✅ Todos los centros reportan equipos ROV en estado Bueno.")

            st.markdown("---")
            st.markdown("#### 🔄 Estado de Rotación Semanal (7 días) por Centro")
            filas_rot = []
            hoy_g = obtener_hora_chile().date()
            for cen_r, info_r in st.session_state.db_rovs_por_centro.items():
                act_id = info_r.get("activo_id", 1)
                eq_r = info_r.get("equipos", {}).get(act_id, {})
                f_i = eq_r.get("fecha_inicio_uso", hoy_g)
                if isinstance(f_i, str):
                    try:
                        f_i = datetime.date.fromisoformat(f_i)
                    except Exception:
                        f_i = hoy_g
                d_uso = max((hoy_g - f_i).days, 0)
                filas_rot.append({
                    "Centro": cen_r,
                    "ROV En Uso": eq_r.get("nombre", "N/A"),
                    "N° Serie": eq_r.get("serie_rov", "N/A"),
                    "Última Mantención": str(eq_r.get("mantencion", "N/A")),
                    "Días en Uso": d_uso,
                    "Estado Rotación": "🚨 ROTACIÓN PENDIENTE" if d_uso >= DIAS_ROTACION_ROV else "✅ Al día"
                })
            if filas_rot:
                st.dataframe(pd.DataFrame(filas_rot), use_container_width=True)

    # ---- TAB 4: ADMINISTRACIÓN ----
    with tab_admin:
        sub_p, sub_c, sub_r, sub_h, sub_reset = st.tabs([
            "👨‍✈️ Pilotos", "⚓ Centros y Fin de Faena", "🤖 Flota ROV", "📜 Historial Mantenciones / Rotaciones", "🧹 Reinicio Oficial"
        ])

        with sub_p:
            st.write("**Añadir o Actualizar Piloto (con Centro Asignado)**")
            centros_lista = list(st.session_state.db_centros_areas.keys())
            with st.form("form_add_piloto_ger", clear_on_submit=True):
                cp1, cp2, cp3, cp4 = st.columns(4)
                with cp1:
                    new_user = st.text_input("Usuario (Ej: Jperez)")
                with cp2:
                    new_rut = st.text_input("RUT (Ej: 12.345.678-9)")
                with cp3:
                    new_pass = st.text_input("Contraseña")
                with cp4:
                    new_cen_pil = st.selectbox("Centro Asignado", centros_lista)
                if st.form_submit_button("Guardar Piloto"):
                    if new_user and new_pass:
                        st.session_state.db_usuarios[new_user] = {
                            "pass": new_pass, "rut": new_rut, "rol": "piloto", "centro": new_cen_pil
                        }
                        guardar_estado_persistente()
                        st.success(f"✅ Piloto {new_user} guardado y asignado a {new_cen_pil}.")
                        st.rerun()

            st.write("**Pilotos Registrados**")
            pilotos_rows = [
                {"Usuario": u, "RUT": d.get("rut", ""), "Centro Asignado": d.get("centro", "")}
                for u, d in st.session_state.db_usuarios.items() if u != "admin"
            ]
            if pilotos_rows:
                st.dataframe(pd.DataFrame(pilotos_rows), use_container_width=True)

            pilotos_elim = [p for p in st.session_state.db_usuarios.keys() if p != "admin"]
            if pilotos_elim:
                col_dp1, col_dp2 = st.columns([3, 1])
                with col_dp1:
                    p_elim = st.selectbox("Seleccione piloto a eliminar", pilotos_elim, key="del_pil_ger")
                with col_dp2:
                    st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                    if st.button("🗑️ Eliminar Piloto", type="primary", use_container_width=True, key="btn_del_pil_ger"):
                        del st.session_state.db_usuarios[p_elim]
                        guardar_estado_persistente()
                        st.success(f"Piloto {p_elim} eliminado.")
                        st.rerun()

        with sub_c:
            st.write("**Añadir o Actualizar Centro y Último Día de Faena (para Alerta de Entrega)**")
            with st.form("form_add_centro_ger", clear_on_submit=True):
                cc1, cc2, cc3, cc4 = st.columns(4)
                with cc1:
                    new_centro = st.text_input("Nombre Centro (Ej: Centro Rowlett)")
                with cc2:
                    new_area = st.text_input("Área (Ej: Área Magallanes)")
                with cc3:
                    new_correo = st.text_input("Correo Responsable")
                with cc4:
                    new_fin_faena = st.date_input("Último Día de Faena (Turno)", value=obtener_hora_chile().date() + datetime.timedelta(days=14))
                if st.form_submit_button("Guardar Centro"):
                    if new_centro and new_correo:
                        st.session_state.db_centros_areas[new_centro] = new_area or "Sin Área"
                        st.session_state.db_centros_correos[new_centro] = new_correo
                        st.session_state.db_centros_fin_faena[new_centro] = new_fin_faena
                        asegurar_rovs_centro(new_centro)
                        guardar_estado_persistente()
                        st.success(f"✅ Centro {new_centro} guardado correctamente.")
                        st.rerun()

            st.write("**Configuración Actual de Centros y Fechas Límite de Entrega de Turno**")
            cen_rows = []
            for c_nom, a_nom in st.session_state.db_centros_areas.items():
                cen_rows.append({
                    "Centro": c_nom,
                    "Área": a_nom,
                    "Correo": st.session_state.db_centros_correos.get(c_nom, ""),
                    "Último Día de Faena": str(st.session_state.db_centros_fin_faena.get(c_nom, "No definido"))
                })
            if cen_rows:
                st.dataframe(pd.DataFrame(cen_rows), use_container_width=True)

            centros_ex = list(st.session_state.db_centros_areas.keys())
            if centros_ex:
                col_dc1, col_dc2 = st.columns([3, 1])
                with col_dc1:
                    c_elim = st.selectbox("Seleccione centro a eliminar", centros_ex, key="del_cen_ger")
                with col_dc2:
                    st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                    if st.button("🗑️ Eliminar Centro", type="primary", use_container_width=True, key="btn_del_cen_ger"):
                        st.session_state.db_centros_areas.pop(c_elim, None)
                        st.session_state.db_centros_correos.pop(c_elim, None)
                        st.session_state.db_centros_fin_faena.pop(c_elim, None)
                        st.session_state.db_rovs_por_centro.pop(c_elim, None)
                        guardar_estado_persistente()
                        st.success(f"Centro {c_elim} eliminado.")
                        st.rerun()

        with sub_r:
            st.write("**Registrar Nuevo Equipo ROV en un Centro**")
            centros_r = list(st.session_state.db_centros_areas.keys())
            with st.form("form_add_rov_ger", clear_on_submit=True):
                rc1, rc2, rc3 = st.columns(3)
                with rc1:
                    sel_c_rov = st.selectbox("Centro", centros_r)
                    n_rov_nom = st.text_input("Nombre (Ej: ROV 3)")
                with rc2:
                    n_rov_ser = st.text_input("N° Serie ROV")
                    n_ctrl_ser = st.text_input("N° Serie Controlador")
                with rc3:
                    n_rov_mant = st.date_input("Fecha Última Mantención", value=obtener_hora_chile().date())
                if st.form_submit_button("Registrar Equipo ROV"):
                    if n_rov_nom and n_rov_ser:
                        info_c = asegurar_rovs_centro(sel_c_rov)
                        nid = max(info_c["equipos"].keys()) + 1 if info_c["equipos"] else 1
                        info_c["equipos"][nid] = {
                            "nombre": n_rov_nom,
                            "serie_rov": n_rov_ser,
                            "serie_ctrl": n_ctrl_ser or n_rov_ser,
                            "mantencion": n_rov_mant,
                            "fecha_inicio_uso": obtener_hora_chile().date(),
                        }
                        guardar_estado_persistente()
                        st.success(f"✅ {n_rov_nom} agregado a {sel_c_rov}.")
                        st.rerun()

        with sub_h:
            st.write("**Historial de Mantenciones Declaradas en Terreno**")
            if st.session_state.historial_mantenciones:
                st.dataframe(pd.DataFrame(st.session_state.historial_mantenciones), use_container_width=True)
            else:
                st.info("Sin mantenciones declaradas aún.")
            st.write("**Historial de Rotaciones de Equipos (Ciclo 7 días)**")
            if st.session_state.historial_rotaciones:
                st.dataframe(pd.DataFrame(st.session_state.historial_rotaciones), use_container_width=True)
            else:
                st.info("Sin rotaciones registradas aún.")

        with sub_reset:
            st.subheader("🧹 Limpieza de Registros de Prueba (Puesta en Marcha Oficial)")
            st.warning(
                "⚠️ Esta acción elimina todos los registros históricos de prueba (Entregas de Turno, HPT, Reportes Diarios, "
                "Mantenciones y Rotaciones locales) para dejar la plataforma en cero lista para operación oficial."
            )
            pin_reset = st.text_input("PIN de Administrador para confirmar reinicio", type="password", key="pin_reset_oficial")
            confirm_reset = st.checkbox("Confirmo que deseo borrar todos los registros de prueba anteriores.", key="chk_reset_oficial")
            if st.button("🗑️ LIMPIAR REGISTROS Y DEJAR APP COMO NUEVA", type="primary", use_container_width=True):
                if pin_reset != CLAVE_ADMIN:
                    st.error("PIN incorrecto.")
                elif not confirm_reset:
                    st.error("Debe marcar la casilla de confirmación.")
                else:
                    st.session_state.local_entrega_history = []
                    st.session_state.local_hpt_history = []
                    st.session_state.local_reportes_history = []
                    st.session_state.historial_mantenciones = []
                    st.session_state.historial_rotaciones = []
                    st.session_state.usar_datos_demo = False
                    if os.path.exists(ARCHIVO_BORRADORES):
                        try:
                            os.remove(ARCHIVO_BORRADORES)
                        except Exception:
                            pass
                    guardar_estado_persistente()
                    errores_supa = []
                    if supabase is not None:
                        for tbl in ("entrega_history", "hpt_history", "reportes_history"):
                            try:
                                supabase.table(tbl).delete().neq("id", -1).execute()
                            except Exception as e_del:
                                errores_supa.append(f"{tbl}: {e_del}")
                    if errores_supa:
                        st.warning(
                            "✅ Datos locales limpiados. En Supabase algunas tablas están protegidas por RLS; "
                            "ejecute el comando SQL `TRUNCATE TABLE entrega_history, hpt_history, reportes_history RESTART IDENTITY;` en Supabase SQL Editor."
                        )
                    else:
                        st.success("✅ Todos los registros locales y de Supabase fueron eliminados. ¡Plataforma lista como nueva!")
                    time.sleep(1.5)
                    st.rerun()


# ==============================================================================
# 6. FLUJO PRINCIPAL DE PANTALLAS
# ==============================================================================
if not st.session_state.logged_in:
    ahora_cl = obtener_hora_chile()
    st.markdown(
        f"""
        <div style='display: flex; justify-content: flex-end; width: 100%; padding-top: 5px;'>
            <div style='background: rgba(15, 55, 105, 0.75); border: 1px solid #00a8cc;
                border-radius: 10px; padding: 6px 14px; color: #ffffff; font-weight: 600; font-size: 14px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.4);'>
                🕒 {ahora_cl.strftime('%d-%m-%Y')} &nbsp;|&nbsp; {ahora_cl.strftime('%H:%M')} hrs (Hora Oficial Chile)
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    col1, col2, col3 = st.columns([3, 2, 3])
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        logo = obtener_ruta_logo()
        if logo and os.path.exists(logo):
            try:
                st.image(logo, use_container_width=True)
            except Exception:
                pass
        else:
            st.markdown("<h1 style='text-align: center; color: #00a8cc;'>⚓ TechTrident</h1>", unsafe_allow_html=True)

        st.markdown("<h3 style='text-align: center; color: white; margin-bottom: 20px;'>Portal Operativo ROV</h3>", unsafe_allow_html=True)

        with st.form("login_form"):
            user = st.text_input("Usuario")
            password = st.text_input("Contraseña", type="password")
            submitted = st.form_submit_button("INGRESAR", use_container_width=True)

            if submitted:
                if user in st.session_state.db_usuarios and str(st.session_state.db_usuarios[user]["pass"]) == str(password):
                    st.session_state.logged_in = True
                    st.session_state.current_user = user
                    st.session_state.current_page = "main_menu"
                    if user == "admin":
                        st.session_state.admin_view_mode = "gerencia"
                    else:
                        st.session_state.centro_piloto_activo = st.session_state.db_usuarios[user].get("centro", "Centro Punta Vergara")
                    st.rerun()
                else:
                    st.error("Credenciales inválidas.")

# ------------------------------------------------------------------------------
# MENÚ PRINCIPAL (SE ADAPTA A PILOTO O A LOS 3 MODOS DEL JEFE/ADMIN)
# ------------------------------------------------------------------------------
elif st.session_state.current_page == "main_menu":
    render_barra_superior_admin()

    # MODO 1: PILOTO REAL O SIMULACIÓN DE VISTA PILOTO PARA EL JEFE
    if (not es_administrador()) or (st.session_state.admin_view_mode == "piloto_demo"):
        st.markdown("<h1 style='text-align: center;'>⚓ Portal de Pilotos — Control de Turno ROV</h1>", unsafe_allow_html=True)
        centros_disp = list(st.session_state.db_centros_areas.keys())

        if es_administrador():
            st.info("👁️ **Modo Simulación Piloto:** Así es exactamente como verán la plataforma los 24 pilotos al iniciar sesión.")
            idx_sim = centros_disp.index(st.session_state.centro_piloto_activo) if st.session_state.centro_piloto_activo in centros_disp else 0
            st.session_state.centro_piloto_activo = st.selectbox("Simular centro del piloto:", centros_disp, index=idx_sim)
            centro_actual = st.session_state.centro_piloto_activo
        else:
            centro_actual = obtener_centro_usuario()

        area_actual = st.session_state.db_centros_areas.get(centro_actual, "N/A")
        st.write(f"👨‍✈️ Operador en turno: **{st.session_state.current_user}** | 📍 Centro asignado: **{centro_actual}** ({area_actual})")

        # Alerta automática de rotación cada 7 días
        render_alerta_rotacion_7_dias(centro_actual)

        st.divider()
        cp1, cp2, cp3 = st.columns(3)
        with cp1:
            if st.button("📋 NUEVA ENTREGA DE TURNO", type="primary", use_container_width=True):
                set_page("entrega_turno")
                st.rerun()
        with cp2:
            if st.button("⚙️ MIS ROVs (SERIES Y ROTACIÓN)", use_container_width=True):
                set_page("gestion_rovs_piloto")
                st.rerun()
        with cp3:
            if st.button("📚 ENTREGAS HISTÓRICAS DEL CENTRO", use_container_width=True):
                set_page("historial_entregas_centro")
                st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown(
                "<p style='text-align: center; font-weight: 600; margin-bottom: 8px; color: #38bdf8 !important;'>"
                "🌊 Accesos Rápidos de Navegación y Clima</p>",
                unsafe_allow_html=True
            )
            cw1, cw2, cw3 = st.columns(3)
            with cw1:
                st.link_button("🌊 Tabla de Mareas", "https://www.tablademareas.com", use_container_width=True)
            with cw2:
                st.link_button("💨 Windguru", "https://www.windguru.cz", use_container_width=True)
            with cw3:
                st.link_button("⚓ SITPORT", "https://sitport.directemar.cl/#/general", use_container_width=True)

        st.markdown("<br>", unsafe_allow_html=True)
        _, c_salir, _ = st.columns([1, 2, 1])
        with c_salir:
            if st.button("🔒 Cerrar Sesión", use_container_width=True):
                st.session_state.logged_in = False
                st.session_state.current_user = ""
                st.session_state.admin_acceso_historial = False
                st.session_state.admin_acceso_graficos = False
                set_page("login")
                st.rerun()

    # MODO 2: PANEL GERENCIAL (JEFE DE OPERACIONES)
    elif st.session_state.admin_view_mode == "gerencia":
        render_panel_gerencial_completo()
        st.divider()
        cg_b1, cg_b2, cg_b3 = st.columns(3)
        with cg_b1:
            if st.button("📋 IR A ENTREGA DE TURNO", use_container_width=True):
                set_page("entrega_turno")
                st.rerun()
        with cg_b2:
            if st.button("📚 HISTORIAL GLOBAL DE DOCUMENTOS", use_container_width=True):
                set_page("modulo_busqueda")
                st.rerun()
        with cg_b3:
            if st.button("🔒 Cerrar Sesión", use_container_width=True):
                st.session_state.logged_in = False
                st.session_state.current_user = ""
                st.session_state.admin_acceso_historial = False
                st.session_state.admin_acceso_graficos = False
                set_page("login")
                st.rerun()

    # MODO 3: SUITE COMPLETA TECHTRIDENT (PARA MOSTRAR TODOS LOS MÓDULOS AL JEFE)
    else:
        st.markdown("<h1 style='text-align: center;'>⚓ TechTrident — Suite Operativa Completa</h1>", unsafe_allow_html=True)
        st.info("💡 **Modo Suite Completa:** Demostración de todos los módulos adicionales disponibles en la plataforma (HPT, Reporte Diario, Informe Consolidado, Correo y Métricas).")
        st.divider()

        c1, c2 = st.columns(2)
        with c1:
            if st.button("⚓ MÓDULO HPT", use_container_width=True):
                set_page("hpt_menu")
                st.rerun()
            if st.button("📋 ENTREGA DE TURNO", use_container_width=True):
                set_page("entrega_turno")
                st.rerun()
            if st.button("📈 GRÁFICOS GERENCIALES (HPT)", use_container_width=True):
                set_page("panel_graficos")
                st.rerun()
        with c2:
            if st.button("🚢 REPORTE DIARIO", use_container_width=True):
                set_page("reporte_diario")
                st.rerun()
            if st.button("📄 INFORME CONSOLIDADO (PDF/Excel)", use_container_width=True):
                set_page("informe_consolidado")
                st.rerun()
            if st.button("📧 REPORTE CORREO", use_container_width=True):
                set_page("reporte_correo")
                st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)
        _, c_btn2, _ = st.columns([1, 2, 1])
        with c_btn2:
            if st.button("📊 HISTORIAL / AUDITORÍA COMPLETA", use_container_width=True):
                set_page("modulo_busqueda")
                st.rerun()
            if st.button("🔒 Cerrar Sesión", use_container_width=True):
                st.session_state.logged_in = False
                st.session_state.current_user = ""
                st.session_state.admin_acceso_historial = False
                st.session_state.admin_acceso_graficos = False
                set_page("login")
                st.rerun()

# ------------------------------------------------------------------------------
# NUEVAS PÁGINAS DE PILOTO: GESTIÓN ROVs E HISTORIAL COMPARTIDO DEL CENTRO
# ------------------------------------------------------------------------------
elif st.session_state.current_page == "gestion_rovs_piloto":
    render_barra_superior_admin()
    render_gestion_rovs_piloto(obtener_centro_usuario())

elif st.session_state.current_page == "historial_entregas_centro":
    render_barra_superior_admin()
    render_historial_entregas_centro(obtener_centro_usuario())

# ------------------------------------------------------------------------------
# MÓDULO: ENTREGA DE TURNO (CON SERIES, MANTENCIÓN, ROTACIÓN 7 DÍAS Y ALERTAS)
# ------------------------------------------------------------------------------
elif st.session_state.current_page == "entrega_turno":
    render_barra_superior_admin()
    st.button("⬅️ Volver al Menú Principal", on_click=set_page, args=("main_menu",))
    st.markdown("<h1 style='text-align: center;'>📋 Panel de Entrega de Turno Operativo</h1>", unsafe_allow_html=True)
    st.divider()

    st.header("1. Información General")
    opciones_centros_et = list(st.session_state.db_centros_areas.keys())
    centro_def = obtener_centro_usuario()
    idx_cet = opciones_centros_et.index(centro_def) if centro_def in opciones_centros_et else 0

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        piloto_entrante = st.text_input("Piloto Entrante")
    with c2:
        piloto_saliente = st.text_input("Piloto Saliente", value=st.session_state.current_user)
    with c3:
        fecha_et = st.date_input("Fecha", obtener_hora_chile().date())
    with c4:
        centro_et = st.selectbox("Centro", opciones_centros_et, index=idx_cet)
    with c5:
        area_et = st.session_state.db_centros_areas.get(centro_et, "Desconocida")
        st.text_input("Área Asignada", value=area_et, disabled=True)

    # Alerta de rotación 7 días para el centro seleccionado
    render_alerta_rotacion_7_dias(centro_et)

    st.markdown("---")
    st.header("2. Gestión de Equipos en Terreno (ROV)")
    info_rovs_et = asegurar_rovs_centro(centro_et)
    equipos_et = info_rovs_et["equipos"]
    opciones_rov = list(equipos_et.keys())
    idx_activo = opciones_rov.index(info_rovs_et["activo_id"]) if info_rovs_et["activo_id"] in opciones_rov else 0

    nuevo_activo = st.selectbox(
        "Seleccionar Equipo en Uso Actual",
        opciones_rov,
        format_func=lambda x: f"{equipos_et[x]['nombre']} (S/N: {equipos_et[x]['serie_rov']})",
        index=idx_activo,
        key=f"et_sel_rov_{centro_et}"
    )
    if nuevo_activo != info_rovs_et["activo_id"]:
        anterior_id = info_rovs_et["activo_id"]
        info_rovs_et["activo_id"] = nuevo_activo
        equipos_et[nuevo_activo]["fecha_inicio_uso"] = obtener_hora_chile().date()
        if anterior_id in equipos_et:
            st.session_state.historial_rotaciones.append({
                "fecha": str(obtener_hora_chile().date()),
                "centro": centro_et,
                "piloto": st.session_state.current_user,
                "equipo_saliente": f"{equipos_et[anterior_id]['nombre']} ({equipos_et[anterior_id]['serie_rov']})",
                "equipo_entrante": f"{equipos_et[nuevo_activo]['nombre']} ({equipos_et[nuevo_activo]['serie_rov']})",
                "dias_uso_anterior": max((obtener_hora_chile().date() - equipos_et[anterior_id].get("fecha_inicio_uso", obtener_hora_chile().date())).days, 0),
            })
        guardar_estado_persistente()
        st.rerun()

    rov_act = equipos_et[info_rovs_et["activo_id"]]
    rov_sby_ids = [r for r in opciones_rov if r != info_rovs_et["activo_id"]]
    rov_sby = equipos_et[rov_sby_ids[0]] if rov_sby_ids else None

    col_r1, col_r2 = st.columns(2)
    with col_r1:
        st.markdown("🟢 **Equipo en USO actual:**")
        st.markdown(
            f"**{rov_act['nombre']}** | N° Serie ROV: `{rov_act['serie_rov']}` <br>Controlador N° Serie: `{rov_act['serie_ctrl']}`",
            unsafe_allow_html=True
        )
        f_mant_act = rov_act.get("mantencion", obtener_hora_chile().date())
        if isinstance(f_mant_act, str):
            f_mant_act = datetime.date.fromisoformat(f_mant_act)
        nueva_fecha_act = st.date_input(f"Última mantención ({rov_act['nombre']})", value=f_mant_act, key=f"mant_act_{centro_et}")
        if nueva_fecha_act != f_mant_act:
            equipos_et[info_rovs_et["activo_id"]]["mantencion"] = nueva_fecha_act
            st.session_state.historial_mantenciones.append({
                "fecha_registro": str(obtener_hora_chile().date()),
                "centro": centro_et,
                "piloto": st.session_state.current_user,
                "equipo": f"{rov_act['nombre']} (S/N: {rov_act['serie_rov']})",
                "fecha_mantencion_declarada": str(nueva_fecha_act)
            })
            guardar_estado_persistente()
            st.success("✅ Fecha de mantención actualizada.")

    with col_r2:
        if rov_sby:
            st.markdown("🟡 **Equipo Stand-by:**")
            st.markdown(
                f"**{rov_sby['nombre']}** | N° Serie ROV: `{rov_sby['serie_rov']}` <br>Controlador N° Serie: `{rov_sby['serie_ctrl']}`",
                unsafe_allow_html=True
            )
            f_mant_sby = rov_sby.get("mantencion", obtener_hora_chile().date())
            if isinstance(f_mant_sby, str):
                f_mant_sby = datetime.date.fromisoformat(f_mant_sby)
            nueva_fecha_sby = st.date_input(f"Última mantención ({rov_sby['nombre']})", value=f_mant_sby, key=f"mant_sby_{centro_et}")
            if nueva_fecha_sby != f_mant_sby:
                equipos_et[rov_sby_ids[0]]["mantencion"] = nueva_fecha_sby
                st.session_state.historial_mantenciones.append({
                    "fecha_registro": str(obtener_hora_chile().date()),
                    "centro": centro_et,
                    "piloto": st.session_state.current_user,
                    "equipo": f"{rov_sby['nombre']} (S/N: {rov_sby['serie_rov']})",
                    "fecha_mantencion_declarada": str(nueva_fecha_sby)
                })
                guardar_estado_persistente()
                st.success("✅ Fecha de mantención actualizada.")
        else:
            st.info("No hay equipo en Stand-by registrado.")

    c6, c7, c8 = st.columns(3)
    with c6:
        estado_equipo = st.selectbox("Estado General del ROV en Uso", ["Bueno", "Regular", "Requiere cambio"])
    with c7:
        estado_controlador = st.selectbox("Estado del Controlador en Uso", ["Bueno", "Regular", "Requiere cambio"])
    with c8:
        estado_umbilical = st.selectbox("Estado del Cable Umbilical", ["Bueno", "Regular", "Requiere cambio"])
    obs_equipos = st.text_area("Observaciones Generales de los Equipos", placeholder="Detalle observaciones generales...")

    with st.container(border=True):
        st.subheader("⚠️ Reporte Específico de Falla en Equipo ROV (En Uso o Stand-by)")
        st.caption("Use esta sección si necesita reportar una falla puntual en cualquier equipo del centro (por ejemplo, está operando con ROV 2 pero el ROV 1 Stand-by tiene una falla).")
        reportar_falla_rov = st.radio(
            "¿Reportar falla específica en algún ROV?",
            ["Sin fallas específicas", "Sí, reportar falla en un ROV"],
            horizontal=True,
            key=f"rad_falla_rov_{centro_et}"
        )
        rov_con_falla_str = ""
        componente_falla_str = ""
        severidad_falla_str = ""
        detalle_falla_str = ""
        if reportar_falla_rov == "Sí, reportar falla en un ROV":
            opciones_falla_rov = []
            for rid_f in opciones_rov:
                eq_f = equipos_et[rid_f]
                tag_estado = "En Uso" if rid_f == info_rovs_et["activo_id"] else "Stand-by"
                opciones_falla_rov.append(f"{eq_f['nombre']} (S/N: {eq_f['serie_rov']}) [{tag_estado}]")
            cf_1, cf_2, cf_3 = st.columns(3)
            with cf_1:
                rov_con_falla_str = st.selectbox("¿De qué ROV es la falla?", opciones_falla_rov, key=f"sel_rov_falla_{centro_et}")
            with cf_2:
                componentes_sel = st.multiselect(
                    "Componente(s) con falla",
                    ["ROV Principal / Propulsores", "Cable Umbilical", "Controlador", "Brazo Grabber", "Cámara / Iluminación", "Batería / Puerto de Carga", "Otro"],
                    default=["ROV Principal / Propulsores"],
                    key=f"ms_comp_falla_{centro_et}"
                )
                componente_falla_str = ", ".join(componentes_sel) if componentes_sel else "ROV Principal"
            with cf_3:
                severidad_falla_str = st.selectbox(
                    "Severidad / Estado",
                    ["Requiere cambio / Fuera de servicio", "Operativo con observación (Regular)"],
                    key=f"sel_sev_falla_{centro_et}"
                )
            detalle_falla_str = st.text_area(
                "Detalle técnico de la falla reportada",
                placeholder="Ej: ROV 1 presenta falla en propulsor vertical o corte en cable umbilical a los 10 metros...",
                key=f"txt_det_falla_{centro_et}"
            )

    st.markdown("---")
    st.header("3. Equipamiento de Terreno")
    st.write("Seleccione los elementos presentes en terreno:")
    c10, c11, c12, c13, c14 = st.columns(5)
    with c10:
        carpa = st.checkbox("Carpa plegable")
    with c11:
        caseta = st.checkbox("Caseta rígida")
    with c12:
        silla = st.checkbox("Silla plegable")
    with c13:
        lona = st.checkbox("Lona")
    with c14:
        estado_equipamiento = st.selectbox("Estado del Equipamiento", ["Bueno", "Regular", "Requiere cambio"])
    obs_equipamiento = st.text_area("Observaciones del Equipamiento", placeholder="Detalle daños...")

    st.markdown("---")
    st.header("4. Inventario de Terreno")
    herramientas_base = {
        "Cuchillo de maniobra con funda (Bahco)": 1,
        "Cuchillo de maniobra sin funda (Bahco)": 1,
        "Araña de recuperación de acero inoxidable": 1,
        "Juego de llaves Allen": 1,
        "Pelacables": 1,
        "Alicate de corte diagonal": 1,
        "Alicate de punta fina (mangos rojo/azul)": 1,
        "Alicate para anillos de retención (circlips)": 1,
        "Alicate universal": 1,
        "Alicate de punta fina pequeño": 1,
        "Destornilladores": 6,
        "Alicate de presión (caimán)": 1,
        "Imán de recuperación (con cáncamo)": 1,
        "Sierra de cuerda": 1,
    }
    materiales_base = {
        "Frasco de vaselina": 1,
        "Tubos de grasa dieléctrica (Loctite)": 3,
        "Paquete de hisopos": 1,
        "Tapones o conectores cilíndricos negros": 3,
        "Adhesivo industrial B-7000": 1,
        "Lata de lubricante penetrante (Afloja Todo)": 1,
        "WD-40": 1,
        "Limpia contacto": 1,
        "Tapones para puerto de carga": 2,
        "Tapón o cubierta cuadrada pequeña": 1,
        "Protectores de sensor": 3,
        "Rollo de cinta de empalme (Splicing tape)": 1,
        "Cartucho de cuchillas de repuesto": 1,
        "Repuestos de brazo manipulador grabber": 4,
        "Cajas con cotonitos": 1,
        "Cinta aislante eléctrica": 1,
        "Tubo de pegamento instantáneo (super glue)": 1,
        "Caja de hojas de repuesto (bisturí Bauker)": 1,
        "Piezas de repuesto grabber (negras)": 4,
    }

    resultados_inventario = {}
    st.subheader("Herramientas")
    col_h1, col_h2 = st.columns(2)
    items_herr = list(herramientas_base.items())
    for i, (item, cant_esperada) in enumerate(items_herr):
        col = col_h1 if i < (len(items_herr) // 2 + len(items_herr) % 2) else col_h2
        with col:
            c_check, c_num = st.columns([3, 1])
            with c_check:
                presente = st.checkbox(item, value=False, key=f"h_{i}")
            with c_num:
                cantidad = st.number_input(
                    "Cant.", min_value=0, max_value=50,
                    value=cant_esperada if presente else 0, step=1,
                    key=f"nh_{i}", disabled=not presente, label_visibility="collapsed"
                )
            resultados_inventario[item] = {"presente": presente, "cantidad": cantidad}

    st.subheader("Materiales de Mantención")
    col_m1, col_m2 = st.columns(2)
    items_mat = list(materiales_base.items())
    for i, (item, cant_esperada) in enumerate(items_mat):
        col = col_m1 if i < (len(items_mat) // 2 + len(items_mat) % 2) else col_m2
        with col:
            c_check, c_num = st.columns([3, 1])
            with c_check:
                presente = st.checkbox(item, value=False, key=f"m_{i}")
            with c_num:
                cantidad = st.number_input(
                    "Cant.", min_value=0, max_value=50,
                    value=cant_esperada if presente else 0, step=1,
                    key=f"nm_{i}", disabled=not presente, label_visibility="collapsed"
                )
            resultados_inventario[item] = {"presente": presente, "cantidad": cantidad}

    st.markdown("---")
    st.header("5. Registro Operativo")
    faena_et = st.text_area("Faena realizada durante el turno de 14 días", height=80)
    alertas_et = st.text_area("Alertas del centro", placeholder="Ej: Rotura en jaula 104, cable dañado...", height=80)
    pendientes_et = st.text_area("Tareas pendientes o a realizar", height=80)
    obs_generales_et = st.text_area("Observaciones Generales", height=80)

    st.markdown("---")
    st.header("6. Evidencia Fotográfica y Firmas")
    st.write("**Fotografías de Equipos ROV**")
    diccionario_fotos_final = {}
    tabs_fotos = st.tabs([f"Fotos {equipos_et[r]['nombre']}" for r in opciones_rov])
    for i, r_id in enumerate(opciones_rov):
        r_nombre = equipos_et[r_id]["nombre"]
        with tabs_fotos[i]:
            c_f1, c_f2, c_f3 = st.columns(3)
            with c_f1:
                f1 = st.file_uploader(f"Puerto de Carga ({r_nombre})", type=["png", "jpg", "jpeg"], key=f"f1_{r_id}")
                if f1:
                    diccionario_fotos_final[f"Puerto de Carga - {r_nombre}"] = f1
            with c_f2:
                f2 = st.file_uploader(f"Puerto de Umbilical ({r_nombre})", type=["png", "jpg", "jpeg"], key=f"f2_{r_id}")
                if f2:
                    diccionario_fotos_final[f"Puerto de Umbilical - {r_nombre}"] = f2
            with c_f3:
                f3 = st.file_uploader(f"Puerto de Sensor ({r_nombre})", type=["png", "jpg", "jpeg"], key=f"f3_{r_id}")
                if f3:
                    diccionario_fotos_final[f"Puerto de Sensor - {r_nombre}"] = f3
            c_f4, c_f5 = st.columns(2)
            with c_f4:
                f4 = st.file_uploader(f"Puerto de Grabber ({r_nombre})", type=["png", "jpg", "jpeg"], key=f"f4_{r_id}")
                if f4:
                    diccionario_fotos_final[f"Puerto de Grabber - {r_nombre}"] = f4
            with c_f5:
                f5 = st.file_uploader(f"Foto General ({r_nombre})", type=["png", "jpg", "jpeg"], key=f"f5_{r_id}")
                if f5:
                    diccionario_fotos_final[f"Foto General - {r_nombre}"] = f5

    st.write("✍️ Firma Piloto ROV Saliente")
    canvas_piloto = crear_canvas_firma(
        fill_color="rgba(255, 255, 255, 0)", stroke_width=2, stroke_color="#000",
        background_color="#FFF", height=120, width=300, drawing_mode="freedraw", key="canvas_et"
    )
    correo_defecto_et = st.session_state.db_centros_correos.get(centro_et, "reportesrovincinel@gmail.com")
    correo_destino_et = st.text_input("Correo electrónico del destinatario", value=correo_defecto_et)

    if st.button("Guardar, Generar PDF y Enviar", type="primary", use_container_width=True):
        if not piloto_saliente or not piloto_entrante:
            st.error("Error: Los campos 'Piloto Entrante' y 'Piloto Saliente' son obligatorios.")
        elif not correo_destino_et:
            st.error("Error: Ingrese el correo del destinatario.")
        else:
            barra_et = st.progress(0, text="⚙️ Compilando Entrega de Turno...")
            lista_equipamiento = [
                item for item, selected in zip(["Carpa plegable", "Caseta rígida", "Silla plegable", "Lona"], [carpa, caseta, silla, lona]) if selected
            ]
            txt_equipamiento = ", ".join(lista_equipamiento) if lista_equipamiento else "Ninguno"
            herr_presentes = [f"{item} ({d['cantidad']})" for item, d in resultados_inventario.items() if item in herramientas_base and d["presente"] and d["cantidad"] > 0]
            herr_faltantes = [item for item, d in resultados_inventario.items() if item in herramientas_base and (not d["presente"] or d["cantidad"] == 0)]
            mat_presentes = [f"{item} ({d['cantidad']})" for item, d in resultados_inventario.items() if item in materiales_base and d["presente"] and d["cantidad"] > 0]
            mat_faltantes = [item for item, d in resultados_inventario.items() if item in materiales_base and (not d["presente"] or d["cantidad"] == 0)]

            rov_uso_str = f"{rov_act['nombre']} (S/N: {rov_act['serie_rov']})"
            rov_sby_str = f"{rov_sby['nombre']} (S/N: {rov_sby['serie_rov']})" if rov_sby else "N/A"

            datos_pdf = {
                "1. Información General": {
                    "Piloto_Entrante": piloto_entrante, "Piloto_Saliente": piloto_saliente,
                    "Fecha": str(fecha_et), "Centro": centro_et, "Área": area_et
                },
                "2. Estado de los Equipos (ROV)": {
                    "ROV_En_Uso": rov_uso_str, "ROV_Stand_by": rov_sby_str,
                    "Estado_General_ROV": estado_equipo, "Estado_Controlador": estado_controlador,
                    "Cable_Umbilical": estado_umbilical, "Observaciones_Equipos": obs_equipos,
                    "ROV_Con_Falla": rov_con_falla_str, "Componente_Falla": componente_falla_str,
                    "Severidad_Falla": severidad_falla_str, "Detalle_Falla": detalle_falla_str
                },
                "3. Terreno": {
                    "Equipamiento_Presente": txt_equipamiento,
                    "Estado_del_Equipamiento": estado_equipamiento,
                    "Observaciones_Equipamiento": obs_equipamiento
                },
                "4. Herramientas": {
                    "Herramientas_Presentes": herr_presentes if herr_presentes else ["Ninguna"],
                    "Herramientas_Faltantes": herr_faltantes if herr_faltantes else ["Ninguna"]
                },
                "5. Materiales de Mantención": {
                    "Materiales_Presentes": mat_presentes if mat_presentes else ["Ninguno"],
                    "Materiales_Faltantes": mat_faltantes if mat_faltantes else ["Ninguno"]
                },
                "6. Operativa de Turno (14 días)": {
                    "Faena_Realizada": faena_et, "Alertas_del_Centro": alertas_et,
                    "Tareas_Pendientes": pendientes_et, "Observaciones_Generales": obs_generales_et
                }
            }

            firma_path_et = f"firma_et_{uuid.uuid4().hex[:6]}.png"
            tiene_firma = procesar_firma(canvas_piloto, firma_path_et)
            nombre_base_et = f"Entrega_Turno_{centro_et.replace(' ', '_')}_{fecha_et}_{uuid.uuid4().hex[:6]}.pdf"

            try:
                if supabase is not None:
                    res_count = supabase.table("entrega_history").select("id", count="exact").execute()
                    correlativo_et = (res_count.count or 0) + 1
                else:
                    correlativo_et = len(st.session_state.local_entrega_history) + 1
            except Exception:
                correlativo_et = len(st.session_state.local_entrega_history) + 1

            hora_chile = obtener_hora_chile()
            folio_et = f"ET-{hora_chile.strftime('%Y%m%d')}-{correlativo_et:03d}-{hora_chile.strftime('%H%M')}"

            try:
                logo_tridentech = obtener_ruta_logo()
                archivo_pdf_et = generar_pdf_entrega(
                    datos_pdf,
                    logo_tridentech,
                    nombre_base_et,
                    firma_path=firma_path_et if tiene_firma else None,
                    diccionario_fotos=diccionario_fotos_final,
                    folio=folio_et,
                    correlativo=correlativo_et
                )

                barra_et.progress(50, text="☁️ Subiendo PDF a la Nube...")
                url_pdf_et_nube = ""
                if supabase is not None:
                    for intento in range(3):
                        try:
                            time.sleep(0.5)
                            with open(archivo_pdf_et, "rb") as f:
                                supabase.storage.from_("documentos").upload(
                                    path=archivo_pdf_et, file=f, file_options={"content-type": "application/pdf"}
                                )
                            url_pdf_et_nube = supabase.storage.from_("documentos").get_public_url(archivo_pdf_et)
                            break
                        except Exception as upload_err:
                            if intento == 2:
                                st.warning(f"Aviso de subida a nube: {upload_err}")
                            time.sleep(1)

                datos_basicos_et = {
                    "fecha": str(fecha_et),
                    "usuario": piloto_saliente,
                    "centro": centro_et,
                    "area": area_et,
                    "tipo_reporte": "Entrega de Turno",
                    "url_documento": url_pdf_et_nube
                }
                datos_completos_et = {
                    **datos_basicos_et,
                    "piloto_entrante": piloto_entrante,
                    "rov_en_uso": rov_uso_str,
                    "estado_rov": estado_equipo,
                    "estado_controlador": estado_controlador,
                    "estado_umbilical": estado_umbilical,
                    "estado_equipamiento": estado_equipamiento,
                    "herramientas_faltantes": ", ".join(herr_faltantes),
                    "materiales_faltantes": ", ".join(mat_faltantes),
                    "alertas_centro": alertas_et,
                    "tareas_pendientes": pendientes_et,
                    "faena_realizada": faena_et,
                    "rov_con_falla": rov_con_falla_str,
                    "componente_falla": componente_falla_str,
                    "severidad_falla": severidad_falla_str,
                    "detalle_falla": detalle_falla_str,
                }
                ok_bd, msg_bd = guardar_entrega_bd(datos_completos_et, datos_basicos_et)
                if not ok_bd:
                    st.warning(f"⚠️ {msg_bd}")

                # Avanza fecha límite del próximo fin de faena (+14 días) si se entregó hoy o después
                f_fin_actual = st.session_state.db_centros_fin_faena.get(centro_et)
                if f_fin_actual and fecha_et >= f_fin_actual:
                    st.session_state.db_centros_fin_faena[centro_et] = fecha_et + datetime.timedelta(days=14)
                    guardar_estado_persistente()

                barra_et.progress(80, text="📧 Transmitiendo Correo...")
                correo_enviado = False
                try:
                    try:
                        remitente = str(st.secrets.get("EMAIL_USER", "")).strip()
                        password = str(st.secrets.get("EMAIL_PASS", "")).strip()
                        servidor_smtp = str(st.secrets.get("SMTP_SERVER", "mail.incinel.cl")).strip()
                        puerto_smtp = int(st.secrets.get("SMTP_PORT", 587))
                    except Exception:
                        remitente = str(os.environ.get("EMAIL_USER", "")).strip()
                        password = str(os.environ.get("EMAIL_PASS", "")).strip()
                        servidor_smtp = str(os.environ.get("SMTP_SERVER", "mail.incinel.cl")).strip()
                        puerto_smtp = int(os.environ.get("SMTP_PORT", 587))

                    if remitente and password:
                        es_alerta_critica = (
                            estado_equipo == "Requiere cambio"
                            or estado_umbilical == "Requiere cambio"
                            or estado_controlador == "Requiere cambio"
                            or (bool(rov_con_falla_str) and "requiere" in severidad_falla_str.lower())
                        )
                        prefijo = "🚨 ALERTA CRÍTICA - " if es_alerta_critica else "INFO: "
                        msg = MIMEMultipart()
                        msg["From"] = remitente
                        msg["To"] = correo_destino_et
                        msg["Bcc"] = ", ".join(CORREOS_OCULTOS + [remitente])
                        msg["Subject"] = f"{prefijo}Entrega de Turno ROV - {centro_et}"
                        msg.attach(MIMEText("Estimados muy buenas tardes, junto con saludar se adjunta entrega formal de turno.", "plain"))

                        with open(archivo_pdf_et, "rb") as attachment:
                            part = MIMEBase("application", "octet-stream")
                            part.set_payload(attachment.read())
                        encoders.encode_base64(part)
                        part.add_header("Content-Disposition", f"attachment; filename={archivo_pdf_et}")
                        msg.attach(part)

                        server = smtplib.SMTP(servidor_smtp, puerto_smtp, timeout=15)
                        server.starttls()
                        server.login(remitente, password)
                        server.send_message(msg)
                        server.quit()
                        correo_enviado = True

                        try:
                            imap = imaplib.IMAP4_SSL(servidor_smtp, 993, timeout=5)
                            imap.login(remitente, password)
                            imap.append("INBOX.Sent", "\\Seen", imaplib.Time2Internaldate(time.time()), msg.as_bytes())
                            imap.logout()
                        except Exception:
                            pass
                except Exception as e_smtp:
                    st.warning(f"El PDF se generó y guardó, pero hubo un retraso de red al enviar el correo: {e_smtp}")

                if os.path.exists(firma_path_et):
                    os.remove(firma_path_et)

                barra_et.progress(100, text="✅ Turno Entregado.")
                time.sleep(0.5)
                barra_et.empty()
                if correo_enviado:
                    st.success(f"✅ Reporte de Entrega de Turno generado, guardado y enviado a {correo_destino_et}.")
                else:
                    st.success("✅ Reporte de Entrega de Turno generado y guardado en el historial del centro.")

                with open(archivo_pdf_et, "rb") as f:
                    st.download_button(
                        "📥 Descargar Copia Local PDF",
                        data=f.read(),
                        file_name=archivo_pdf_et,
                        mime="application/pdf",
                        use_container_width=True
                    )
            except Exception as e:
                barra_et.empty()
                st.error(f"Error Técnico: {e}")

# ------------------------------------------------------------------------------
# MÓDULO: INFORME CONSOLIDADO (SUITE COMPLETA)
# ------------------------------------------------------------------------------
elif st.session_state.current_page == "informe_consolidado":
    render_barra_superior_admin()
    st.button("⬅️ Volver al Menú Principal", on_click=set_page, args=("main_menu",))
    st.markdown("<h1 style='text-align: center;'>📄 Informe Consolidado Operativo (PDF Detallado)</h1>", unsafe_allow_html=True)
    st.info("Este módulo genera el archivo PDF formal con la planimetría y el registro fotográfico, además del Excel semanal de respaldo.")
    st.divider()

    if "historial_excel_semanal" not in st.session_state:
        st.session_state.historial_excel_semanal = pd.DataFrame(columns=[
            "Fecha", "Semana", "Jaula", "Centro", "Tipo Red", "Anomalia", "Ubicacion", "Profundidad", "Estado"
        ])

    tab1, tab2, tab3 = st.tabs(["1️⃣ Contexto y Operativa", "2️⃣ Registro de Anomalías (Fotos)", "3️⃣ Compilar PDF y Texto Correo"])
    with tab1:
        st.subheader("Datos de la Inspección")
        c1, c2, c3 = st.columns(3)
        with c1:
            ic_cliente = st.selectbox("Empresa / Cliente", ["Salmones Blumar", "Salmones Blumar Magallanes", "Otra Empresa"], key="ic_cl")
            opciones_centros = list(st.session_state.db_centros_areas.keys())
            ic_centro = st.selectbox("Centro de Cultivo", opciones_centros, key="ic_ce")
            ic_fecha = st.date_input("Fecha de Inspección", value=obtener_hora_chile().date(), key="ic_fe")
        with c2:
            ic_encargado = st.text_input("Asistente/Encargado de Centro", value=st.session_state.ic_data.get("encargado", ""), key="ic_en")
            ic_piloto = st.text_input("Piloto ROV", value=st.session_state.current_user, key="ic_pi")
            ic_equipo = st.selectbox("Equipo ROV Utilizado", ["Deep Trekker DTG3", "MC Petrohue", "Chasing Promax", "Fifish vs xpert"], key="ic_eq")
        with c3:
            ic_disponibilidad = st.selectbox("Disponibilidad", ["Disponible", "Enfermo", "Licencia Médica", "No disponible"], key="ic_di")
            ic_ingreso = st.date_input("Fecha último ingreso", key="ic_in")
            ic_proximo = st.date_input("Fecha próximo ingreso", key="ic_pr")

        c4, c5, c6 = st.columns(3)
        with c4:
            ic_dias_cerrado = st.number_input("Días puerto cerrado", min_value=0, value=0, key="ic_dc")
            ic_dias_fallas = st.number_input("Días fallas ROV", min_value=0, value=0, key="ic_df")
        with c5:
            ic_backup = st.radio("Backup Operativo", ["SI", "NO"], horizontal=True, key="ic_bk")
            ic_graber = st.radio("Graber Operativo", ["SI", "NO"], horizontal=True, key="ic_gr")
        with c6:
            ic_planimetria = st.file_uploader("Subir Esquema/Planimetría del Centro", type=["jpg", "jpeg", "png"], key="ic_pl")

        st.subheader("Actividades Diarias")
        col_act1, col_act2 = st.columns(2)
        with col_act1:
            ic_act_am = st.text_area("Actividad AM", placeholder="Ej: INSPECCIÓN PECERA J101...", key="ic_aam")
        with col_act2:
            ic_act_pm = st.text_area("Actividad PM", placeholder="Ej: EXTRACCIÓN MORTALIDAD J101...", key="ic_apm")

        if st.button("Guardar Datos Generales", type="primary", key="ic_save"):
            dias_trabajados = max((obtener_hora_chile().date() - ic_ingreso).days + 1, 1)
            st.session_state.ic_data.update({
                "cliente": ic_cliente, "centro": ic_centro, "fecha": ic_fecha,
                "encargado": ic_encargado, "piloto": ic_piloto, "equipo": ic_equipo,
                "disponibilidad": ic_disponibilidad, "ingreso": ic_ingreso, "proximo": ic_proximo,
                "dias_trabajados": dias_trabajados, "dias_cerrado": ic_dias_cerrado, "dias_fallas": ic_dias_fallas,
                "backup": ic_backup, "graber": ic_graber, "actividad_am": ic_act_am, "actividad_pm": ic_act_pm,
                "planimetria": ic_planimetria.getvalue() if ic_planimetria else st.session_state.ic_data.get("planimetria")
            })
            st.success("✅ Datos operativos guardados exitosamente. Pasa a la pestaña 2.")

    with tab2:
        st.subheader("Registro Dinámico de Roturas/Anomalías")
        with st.form("form_anomalia", clear_on_submit=True):
            col_a1, col_a2 = st.columns(2)
            with col_a1:
                jaula = st.text_input("N° de Jaula (Ej: 101, 102)")
                tipo_red = st.selectbox("Tipo de Red", ["Lobera", "Pecera", "Pajarera"])
                desc = st.text_area("Descripción de la Anomalía (Ej: Rotura 2x1 cuadros)")
            with col_a2:
                ubicacion = st.text_input("Ubicación (Ej: Lateral Este, Fondo, Cabecera)")
                profundidad = st.number_input("Profundidad (metros)", min_value=0.0, step=0.1)
                estado = st.selectbox("Estado", ["Reparada", "Pendiente"])
            st.markdown("**Evidencia Fotográfica**")
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                foto_antes = st.file_uploader("Foto Antes (Rotura/Hallazgo)", type=["jpg", "jpeg", "png"], key="ic_f1")
            with col_f2:
                foto_despues = st.file_uploader("Foto Después (Reparación)", type=["jpg", "jpeg", "png"], key="ic_f2")
            if st.form_submit_button("➕ Agregar a la Matriz", use_container_width=True):
                if not jaula or not desc:
                    st.error("La Jaula y la Descripción son obligatorias.")
                else:
                    nueva_anomalia = {
                        "id": str(uuid.uuid4())[:6], "jaula": jaula, "tipo_red": tipo_red,
                        "descripcion": desc, "ubicacion": ubicacion, "profundidad": profundidad,
                        "estado": estado,
                        "foto_rotura": foto_antes.getvalue() if foto_antes else None,
                        "foto_reparacion": foto_despues.getvalue() if foto_despues else None
                    }
                    st.session_state.anomalias.append(nueva_anomalia)
                    semana_actual = obtener_hora_chile().date().isocalendar()[1]
                    nueva_fila = pd.DataFrame([{
                        "Fecha": obtener_hora_chile().date(), "Semana": semana_actual, "Jaula": jaula,
                        "Centro": st.session_state.ic_data.get("centro", "N/A"), "Tipo Red": tipo_red,
                        "Anomalia": desc, "Ubicacion": ubicacion, "Profundidad": profundidad, "Estado": estado
                    }])
                    st.session_state.historial_excel_semanal = pd.concat(
                        [st.session_state.historial_excel_semanal, nueva_fila], ignore_index=True
                    )
                    st.success(f"✅ Registrado exitosamente en Jaula {jaula}.")

        st.markdown("---")
        st.markdown(f"### Anomalías en Memoria ({len(st.session_state.anomalias)})")
        if not st.session_state.anomalias:
            st.info("No hay anomalías registradas hoy.")
        else:
            for i, an in enumerate(st.session_state.anomalias):
                with st.container(border=True):
                    c_an1, c_an2 = st.columns([5, 1])
                    with c_an1:
                        st.markdown(f"**Jaula {an['jaula']} ({an['tipo_red']}) - {an['estado']}**")
                        st.write(f"{an['descripcion']} | Prof: {an['profundidad']}m | Ubicación: {an['ubicacion']}")
                    with c_an2:
                        if st.button("X", key=f"del_{an['id']}", use_container_width=True):
                            st.session_state.anomalias.pop(i)
                            st.rerun()

    with tab3:
        st.subheader("Paso Final: Compilación")
        ic_observaciones = st.text_area("Observaciones Generales de la Inspección", height=100, key="ic_obs")
        col_gen1, col_gen2 = st.columns(2)
        with col_gen1:
            if st.button("1. GENERAR INFORME DETALLADO (PDF)", type="primary", use_container_width=True, key="btn_pdf_ic"):
                if not st.session_state.ic_data:
                    st.error("⚠️ Guarde los datos de contexto en la Pestaña 1 primero.")
                else:
                    st.session_state.ic_data["observaciones"] = ic_observaciones
                    with st.spinner("Compilando PDF..."):
                        nombre_pdf = f"INFORME_DIARIO_{str(st.session_state.ic_data.get('centro', 'Centro')).replace(' ', '_')}_{st.session_state.ic_data.get('fecha')}.pdf"
                        try:
                            logo_path = obtener_ruta_logo()
                            rov_cover = "rov_cover.jpg" if os.path.exists("rov_cover.jpg") else None
                            pdf_generado = generar_pdf_consolidado(
                                datos=st.session_state.ic_data,
                                anomalias=st.session_state.anomalias,
                                logo_filename=logo_path,
                                rov_cover=rov_cover,
                                nombre_archivo=nombre_pdf
                            )
                            st.session_state.ic_pdf_generado = pdf_generado
                            st.success("✅ PDF Generado con Éxito.")
                        except Exception as e:
                            st.error(f"Falla técnica al generar el PDF: {e}")

            if st.session_state.get("ic_pdf_generado") and os.path.exists(st.session_state.ic_pdf_generado):
                with open(st.session_state.ic_pdf_generado, "rb") as f:
                    st.download_button(
                        "📥 Descargar Informe PDF", data=f,
                        file_name=st.session_state.ic_pdf_generado, mime="application/pdf",
                        use_container_width=True, key="dl_pdf_ic"
                    )
        with col_gen2:
            if st.button("2. GENERAR TEXTO PARA CORREO", use_container_width=True, key="btn_txt_ic"):
                if not st.session_state.ic_data:
                    st.error("Faltan datos de contexto en Pestaña 1.")
                else:
                    data = st.session_state.ic_data
                    texto_correo = (
                        f"CENTRO: {data.get('centro', '')}\n"
                        f"NOMBRE ASISTENTE/J.CENTRO: {data.get('encargado', '')}\n"
                        f"NOMBRE OPERADOR: {data.get('piloto', '')}\n"
                        f"DISPONIBLE: {data.get('disponibilidad', '')}\n"
                        f"FECHA ULTIMO INGRESO: {data.get('ingreso', obtener_hora_chile().date()).strftime('%d-%m-%Y')}\n"
                        f"FECHA PROXIMO INGRESO: {data.get('proximo', obtener_hora_chile().date()).strftime('%d-%m-%Y')}\n"
                        f"DIAS TRABAJADOS CENTRO: {data.get('dias_trabajados', 1)}\n"
                        f"DIAS PUERTO CERRADO: {data.get('dias_cerrado', 0)}\n"
                        f"DIAS FALLAS ROV: {data.get('dias_fallas', 0)}\n"
                        f"BACKUP OPERATIVO: {data.get('backup', '')}\n"
                        f"GRABER OPERATIVO: {data.get('graber', '')}\n"
                        f"ACTIVIDAD AM: {data.get('actividad_am', '')}\n"
                        f"ACTIVIDAD PM: {data.get('actividad_pm', '')}\n"
                        f"OBSERVACIONES: {ic_observaciones}\n"
                    )
                    st.code(texto_correo, language="text")

# ------------------------------------------------------------------------------
# MÓDULO: REPORTE CORREO (SUITE COMPLETA)
# ------------------------------------------------------------------------------
elif st.session_state.current_page == "reporte_correo":
    render_barra_superior_admin()
    st.button("⬅️ Volver al Menú Principal", on_click=set_page, args=("main_menu",))
    st.markdown("<h1 style='text-align: center;'>📧 Generador de Reporte para Correo</h1>", unsafe_allow_html=True)
    st.divider()

    with st.form("form_reporte_correo"):
        st.subheader("Datos de la Jornada")
        col1, col2 = st.columns(2)
        with col1:
            opciones_centros = list(st.session_state.db_centros_areas.keys())
            centro = st.selectbox("Centro", opciones_centros)
            nombre_jefe = st.text_input("Nombre Asistente/J.Centro")
            nombre_operador = st.text_input("Nombre Operador (Piloto ROV)", value=st.session_state.current_user)
            disponibilidad = st.selectbox("Estado de Disponibilidad", ["Disponible", "No disponible", "Licencia médica", "Enfermo"])
        with col2:
            fecha_ingreso = st.date_input("Fecha último ingreso (Inicio de turno)")
            fecha_proximo = st.date_input("Fecha próximo ingreso (Próximo turno)")
            dias_cerrado = st.number_input("Días puerto cerrado", min_value=0, value=0)
            dias_fallas = st.number_input("Días fallas ROV", min_value=0, value=0)
        col3, col4 = st.columns(2)
        with col3:
            backup = st.radio("¿Backup Operativo?", ["SI", "NO"], horizontal=True)
        with col4:
            graber = st.radio("¿Graber Operativo?", ["SI", "NO"], horizontal=True)
        st.subheader("Resumen de Actividades")
        actividad_am = st.text_area("Actividad AM", placeholder="Ej: INSPECCIÓN PECERA J101-J102...")
        actividad_pm = st.text_area("Actividad PM", placeholder="Ej: EXTRACCIÓN MORTALIDAD J101...")
        observaciones = st.text_area("Observaciones", placeholder="Ej: SE ENCUENTRA ROTURA PECERA J102, 4X2...")
        submit_correo = st.form_submit_button("GENERAR TEXTO PARA CORREO", use_container_width=True)

    if submit_correo:
        dias_trabajados = max((obtener_hora_chile().date() - fecha_ingreso).days + 1, 1)
        texto_correo = (
            f"CENTRO: {centro}\n"
            f"NOMBRE ASISTENTE/J.CENTRO: {nombre_jefe}\n"
            f"NOMBRE OPERADOR: {nombre_operador}\n"
            f"DISPONIBLE: {disponibilidad}\n"
            f"FECHA ULTIMO INGRESO: {fecha_ingreso.strftime('%d-%m-%Y')}\n"
            f"FECHA PROXIMO INGRESO: {fecha_proximo.strftime('%d-%m-%Y')}\n"
            f"DIAS TRABAJADOS CENTRO: {dias_trabajados}\n"
            f"DIAS PUERTO CERRADO: {dias_cerrado}\n"
            f"DIAS FALLAS ROV: {dias_fallas}\n"
            f"BACKUP OPERATIVO: {backup}\n"
            f"GRABER OPERATIVO: {graber}\n"
            f"ACTIVIDAD AM: {actividad_am}\n"
            f"ACTIVIDAD PM: {actividad_pm}\n"
            f"OBSERVACIONES: {observaciones}\n"
        )
        datos_guardados = {
            "Fecha": obtener_hora_chile().date(), "Centro": centro, "Asistente/J.Centro": nombre_jefe,
            "Operador": nombre_operador, "Disponibilidad": disponibilidad, "Ingreso": fecha_ingreso,
            "Dias Trabajados": dias_trabajados, "Dias P. Cerrado": dias_cerrado, "Dias Fallas": dias_fallas,
            "Backup": backup, "Graber": graber, "Actividad AM": actividad_am,
            "Actividad PM": actividad_pm, "Observaciones": observaciones
        }
        st.session_state.historial_reportes_correo.append(datos_guardados)
        st.success("✅ ¡Texto generado exitosamente!")
        st.code(texto_correo, language="text")

    st.divider()
    st.subheader("Acciones de Fin de Semana")
    if st.session_state.historial_reportes_correo:
        df_correo = pd.DataFrame(st.session_state.historial_reportes_correo)
        exportado_excel = False
        for eng in ("xlsxwriter", "openpyxl"):
            try:
                buffer_correo = io.BytesIO()
                with pd.ExcelWriter(buffer_correo, engine=eng) as writer:
                    df_correo.to_excel(writer, index=False, sheet_name="Actividades Diarias")
                st.download_button(
                    label="📊 DESCARGAR CONSOLIDADO SEMANAL (EXCEL)",
                    data=buffer_correo.getvalue(),
                    file_name=f"Consolidado_Actividades_{obtener_hora_chile().date()}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
                exportado_excel = True
                break
            except Exception:
                continue
        if not exportado_excel:
            st.download_button(
                label="📊 DESCARGAR CONSOLIDADO SEMANAL (CSV)",
                data=df_correo.to_csv(index=False).encode("utf-8"),
                file_name=f"Consolidado_Actividades_{obtener_hora_chile().date()}.csv",
                mime="text/csv",
                use_container_width=True
            )
        if st.button("🗑️ Limpiar registros (Usar el lunes)", use_container_width=True):
            st.session_state.historial_reportes_correo = []
            st.rerun()
    else:
        st.warning("No hay registros diarios guardados para generar el consolidado esta semana.")

# ------------------------------------------------------------------------------
# MÓDULO HPT (MENÚ + 4 PASOS CON BORRADOR PERSISTENTE)
# ------------------------------------------------------------------------------
elif st.session_state.current_page == "hpt_menu":
    render_barra_superior_admin()
    st.button("⬅️ Volver al Menú Principal", on_click=set_page, args=("main_menu",))
    st.markdown("<h1 style='text-align: center;'>⚓ Módulo HPT</h1>", unsafe_allow_html=True)
    st.divider()

    borradores = obtener_almacen_borradores()
    user_actual = st.session_state.current_user
    if user_actual in borradores:
        info_b = borradores[user_actual]
        with st.container(border=True):
            st.info(
                f"💾 **Tienes una HPT guardada en borrador** (Centro: **{info_b['data'].get('centro', 'N/A')}** | "
                f"Paso {info_b['step']}/4 | Guardada el: {info_b.get('guardado_el', 'Hoy')})"
            )
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                if st.button("📂 ABRIR Y CONTINUAR HPT GUARDADA", type="primary", use_container_width=True):
                    st.session_state.hpt_data = info_b["data"].copy()
                    st.session_state.hpt_step = info_b["step"]
                    st.session_state.hpt_pdf_generado = None
                    set_page("hpt_nuevo")
                    st.rerun()
            with col_b2:
                if st.button("🗑️ DESCARTAR BORRADOR", use_container_width=True):
                    eliminar_borrador_usuario(user_actual)
                    st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("➕ CREAR NUEVA HPT DESDE CERO", use_container_width=True):
        set_step(1)
        st.session_state.hpt_pdf_generado = None
        opciones_c = list(st.session_state.db_centros_areas.keys())
        st.session_state.hpt_data = {
            "empresa": "Salmones Blumar Magallanes",
            "fecha": obtener_hora_chile().date(),
            "hora_inicio": RANGOS_INICIO[2],
            "hora_termino": RANGO_TERMINO[2],
            "centro": opciones_c[0] if opciones_c else "",
            "correo": "", "encargado": "", "ponton": "", "condicion_puerto": "Abierto",
            "tarea": "", "trabajo_rutinario": "Sí",
            "epp": [False] * 7, "faena": "Inspeccion Red pecera", "erc": [False] * 6,
            "tc_duracion": "15 minutos", "tc_hora": "07:45", "tc_nombre": "Faena diaria",
            "tc_fecha": obtener_hora_chile().date(),
            "check_instruido": "Sí", "check_clima": "Sí", "check_equipos": "Sí", "check_orden": "Sí",
            "evidencia_puerto": None, "prevencion_1": "", "prevencion_2": ""
        }
        set_page("hpt_nuevo")
        st.rerun()

elif st.session_state.current_page == "hpt_nuevo":
    render_barra_superior_admin()
    barra_superior = st.container()
    st.markdown(f"<h1 style='text-align: center;'>Nueva HPT - Paso {st.session_state.hpt_step}</h1>", unsafe_allow_html=True)
    st.progress(st.session_state.hpt_step / 4.0)
    datos_paso_actual = {}

    if st.session_state.hpt_step == 1:
        st.subheader("Datos Operativos")
        opciones_empresa = ["Salmones Blumar Magallanes", "Salmones Blumar"]
        idx_empresa = opciones_empresa.index(st.session_state.hpt_data.get("empresa", opciones_empresa[0])) if st.session_state.hpt_data.get("empresa") in opciones_empresa else 0
        empresa = st.selectbox("Empresa", opciones_empresa, index=idx_empresa)

        col1, col2 = st.columns(2)
        with col1:
            fecha = st.date_input("Fecha", value=st.session_state.hpt_data.get("fecha", obtener_hora_chile().date()))
            idx_hi = RANGOS_INICIO.index(st.session_state.hpt_data["hora_inicio"]) if st.session_state.hpt_data["hora_inicio"] in RANGOS_INICIO else 0
            hora_inicio = st.selectbox("Hora de Inicio", RANGOS_INICIO, index=idx_hi)
            encargado = st.text_input("Encargado del Centro", value=st.session_state.hpt_data.get("encargado", ""))
            ponton = st.text_input("Nombre Pontón", value=st.session_state.hpt_data.get("ponton", ""))
            opciones_rutinario = ["Sí", "No"]
            idx_rut = opciones_rutinario.index(st.session_state.hpt_data.get("trabajo_rutinario", "Sí")) if st.session_state.hpt_data.get("trabajo_rutinario") in opciones_rutinario else 0
            trabajo_rutinario = st.radio("¿Trabajo Rutinario?", opciones_rutinario, index=idx_rut, horizontal=True)

        with col2:
            opciones_centros = list(st.session_state.db_centros_areas.keys())
            idx_centro = opciones_centros.index(st.session_state.hpt_data.get("centro", opciones_centros[0])) if st.session_state.hpt_data.get("centro") in opciones_centros else 0
            centro = st.selectbox("Centro de Cultivo", opciones_centros, index=idx_centro)
            idx_ht = RANGO_TERMINO.index(st.session_state.hpt_data["hora_termino"]) if st.session_state.hpt_data["hora_termino"] in RANGO_TERMINO else 0
            hora_termino = st.selectbox("Hora de Término", RANGO_TERMINO, index=idx_ht)
            opciones_puerto_hpt = ["Abierto", "Cerrado para naves menores", "Cerrado total"]
            idx_puerto = opciones_puerto_hpt.index(st.session_state.hpt_data.get("condicion_puerto", "Abierto")) if st.session_state.hpt_data.get("condicion_puerto") in opciones_puerto_hpt else 0
            condicion_puerto = st.selectbox("Condición de Puerto", opciones_puerto_hpt, index=idx_puerto)
            st.link_button("🌐 Revisar SITPORT (Directemar)", "https://sitport.directemar.cl/#/general", use_container_width=True)
            evidencia_img = None
            if condicion_puerto in ["Cerrado para naves menores", "Cerrado total"]:
                evidencia_img = st.file_uploader("📸 Evidencia fotográfica de puerto cerrado", type=["png", "jpg", "jpeg"])

        area_asignada = st.session_state.db_centros_areas.get(centro, "Desconocida")
        st.info(f"⚓ Área Asignada: **{area_asignada}**")
        correo = ""

        st.markdown("🔒 **Asesores de Prevención y Operaciones**")
        col3, col4 = st.columns(2)
        with col3:
            prev_1 = st.text_input("Prevención 1", value=st.session_state.hpt_data.get("prevencion_1", ""))
        with col4:
            prev_2 = st.text_input("Prevención 2", value=st.session_state.hpt_data.get("prevencion_2", ""))

        opciones_faena = [
            "Inspeccion Red Lobera", "Inspeccion Red pecera", "Inspeccion Tensores",
            "Recuperacion inorganico", "Apoyo Centro de cultivo", "Apoyo team buceo",
            "Extraccion de mortalidad", "Mantencion equipos", "Mantencion equipos rov",
            "Malas condiciones climaticas", "Sin faena"
        ]
        if condicion_puerto == "Cerrado total":
            st.warning("⚠️ **Puerto Cerrado Total:** Se saltarán los pasos de EPP y ERC.")
            faena = "Sin faena"
            tarea = "Puerto Cerrado Total. Sin operaciones."
        else:
            idx_faena = opciones_faena.index(st.session_state.hpt_data.get("faena", opciones_faena[0])) if st.session_state.hpt_data.get("faena") in opciones_faena else 0
            faena = st.selectbox("Faena a realizar", opciones_faena, index=idx_faena)
            tarea = st.text_area("Detalles de faena y lugar", value=st.session_state.hpt_data.get("tarea", ""))

        img_bytes_actual = evidencia_img.getvalue() if evidencia_img else st.session_state.hpt_data.get("evidencia_puerto")
        datos_paso_actual = {
            "empresa": empresa, "fecha": fecha, "hora_inicio": hora_inicio, "hora_termino": hora_termino,
            "centro": centro, "area": area_asignada, "correo": correo, "encargado": encargado,
            "ponton": ponton, "condicion_puerto": condicion_puerto, "faena": faena, "tarea": tarea,
            "trabajo_rutinario": trabajo_rutinario, "evidencia_puerto": img_bytes_actual,
            "prevencion_1": prev_1, "prevencion_2": prev_2
        }
        if st.button("SIGUIENTE ➡️", use_container_width=True):
            st.session_state.hpt_data.update(datos_paso_actual)
            set_step(4 if condicion_puerto == "Cerrado total" else 2)
            st.rerun()

    elif st.session_state.hpt_step == 2:
        st.subheader("Checklist EPP")
        st.markdown("<p style='color: #38bdf8 !important;'>⚠️ Los elementos con (*) son estrictamente obligatorios.</p>", unsafe_allow_html=True)
        estado_epp = st.session_state.hpt_data["epp"]
        col1, col2 = st.columns(2)
        with col1:
            epp_guantes = st.checkbox("Guantes", value=estado_epp[0])
            epp_chaleco = st.checkbox("Chaleco Salvavidas *", value=estado_epp[1])
            epp_zapatos = st.checkbox("Zapatos de seguridad / Botas", value=estado_epp[2])
            epp_termica = st.checkbox("Ropa Térmica *", value=estado_epp[3])
        with col2:
            epp_traje = st.checkbox("Traje de Agua", value=estado_epp[4])
            epp_comunicacion = st.checkbox("Medios de Comunicación *", value=estado_epp[5])
            epp_botiquin = st.checkbox("Botiquín *", value=estado_epp[6])

        datos_paso_actual = {"epp": [epp_guantes, epp_chaleco, epp_zapatos, epp_termica, epp_traje, epp_comunicacion, epp_botiquin]}
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("⬅️ ATRÁS", key="back2", use_container_width=True):
                st.session_state.hpt_data.update(datos_paso_actual)
                set_step(1)
                st.rerun()
        with col_btn2:
            if st.button("SIGUIENTE ➡️", key="next2", use_container_width=True):
                if not (epp_chaleco and epp_termica and epp_comunicacion and epp_botiquin):
                    st.error("⚠️ No cumple con EPP mínimos.")
                else:
                    st.session_state.hpt_data.update(datos_paso_actual)
                    set_step(3)
                    st.rerun()

    elif st.session_state.hpt_step == 3:
        st.subheader("Evaluación de Riesgos y Controles")
        opc_val = ["Sí", "No", "N/A"]
        val1 = opc_val.index(st.session_state.hpt_data.get("check_instruido", "Sí")) if st.session_state.hpt_data.get("check_instruido") in opc_val else 0
        check_instruido = st.radio("¿El personal está instruido en el Procedimiento Específico (Charla 5 min)?", opc_val, index=val1, horizontal=True)
        val2 = opc_val.index(st.session_state.hpt_data.get("check_clima", "Sí")) if st.session_state.hpt_data.get("check_clima") in opc_val else 0
        check_clima = st.radio("¿Condiciones ambientales (viento, lluvia, oleaje) evaluadas y seguras?", opc_val, index=val2, horizontal=True)
        val3 = opc_val.index(st.session_state.hpt_data.get("check_equipos", "Sí")) if st.session_state.hpt_data.get("check_equipos") in opc_val else 0
        check_equipos = st.radio("¿Equipos de apoyo y comunicación operativos y revisados?", opc_val, index=val3, horizontal=True)
        val4 = opc_val.index(st.session_state.hpt_data.get("check_orden", "Sí")) if st.session_state.hpt_data.get("check_orden") in opc_val else 0
        check_orden = st.radio("¿El área de trabajo se encuentra ordenada, despejada y delimitada?", opc_val, index=val4, horizontal=True)
        st.divider()

        estado_erc = st.session_state.hpt_data["erc"]
        st.markdown("**Checklist Riesgos Críticos (ERC)**")
        col1, col2 = st.columns(2)
        with col1:
            erc_izaje = st.checkbox("Izaje", value=estado_erc[0])
            erc_buceo = st.checkbox("Buceo", value=estado_erc[1])
            erc_electricos = st.checkbox("Intervención Equipos Eléctricos", value=estado_erc[2])
        with col2:
            erc_caidas = st.checkbox("Caídas al mismo/distinto nivel", value=estado_erc[3])
            erc_navegacion = st.checkbox("Navegación Diurna/Nocturna", value=estado_erc[4])
            erc_atrapamiento = st.checkbox("Atrapamiento", value=estado_erc[5])

        datos_paso_actual = {
            "erc": [erc_izaje, erc_buceo, erc_electricos, erc_caidas, erc_navegacion, erc_atrapamiento],
            "check_instruido": check_instruido, "check_clima": check_clima,
            "check_equipos": check_equipos, "check_orden": check_orden
        }
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("⬅️ ATRÁS", key="back3", use_container_width=True):
                st.session_state.hpt_data.update(datos_paso_actual)
                set_step(2)
                st.rerun()
        with col_btn2:
            if st.button("SIGUIENTE ➡️", key="next3", use_container_width=True):
                st.session_state.hpt_data.update(datos_paso_actual)
                set_step(4)
                st.rerun()

    elif st.session_state.hpt_step == 4:
        st.subheader("Validación Final")
        with st.expander("Toma de Conocimiento", expanded=True):
            tc_nombre = st.text_input("Nombre Difusión", value=st.session_state.hpt_data.get("tc_nombre", "Faena diaria"))
            col1, col2 = st.columns(2)
            with col1:
                tc_fecha = st.date_input("Fecha Difusión", value=st.session_state.hpt_data.get("tc_fecha", obtener_hora_chile().date()))
                tc_relator = st.text_input("Nombre Relator (Piloto)", value=st.session_state.current_user)
                rut_defecto = st.session_state.db_usuarios.get(st.session_state.current_user, {}).get("rut", "")
                tc_rut = st.text_input("RUT Relator", value=rut_defecto)
            with col2:
                hora_guardada = st.session_state.hpt_data.get("tc_hora", "07:45")
                idx_hora_dif = RANGO_HORA_DIFUSION.index(hora_guardada) if hora_guardada in RANGO_HORA_DIFUSION else (RANGO_HORA_DIFUSION.index("07:45") if "07:45" in RANGO_HORA_DIFUSION else 0)
                tc_hora = st.selectbox("Hora Difusión", RANGO_HORA_DIFUSION, index=idx_hora_dif)
                idx_dur = RANGO_DURACION.index(st.session_state.hpt_data.get("tc_duracion", "15 minutos")) if st.session_state.hpt_data.get("tc_duracion", "15 minutos") in RANGO_DURACION else 2
                tc_duracion = st.selectbox("Duración Difusión", RANGO_DURACION, index=idx_dur)

        with st.expander("Firmas de Responsabilidad", expanded=True):
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                st.write("Firma Supervisor Servicio (Piloto)")
                firma_sup_serv = crear_canvas_firma(
                    stroke_width=2, stroke_color="#000", background_color="#FFF",
                    height=150, width=300, key=f"firma_serv_{st.session_state.reset_firma_piloto_hpt}"
                )
                if st.button("🔄 Reiniciar Firma Piloto", key="btn_reset_piloto", use_container_width=True):
                    st.session_state.reset_firma_piloto_hpt += 1
                    st.rerun()
            with col_f2:
                st.write("Firma Encargado de Centro")
                firma_encargado = crear_canvas_firma(
                    stroke_width=2, stroke_color="#000", background_color="#FFF",
                    height=150, width=300, key=f"firma_encargado_{st.session_state.reset_firma_encargado_hpt}"
                )
                if st.button("🔄 Reiniciar Firma Encargado", key="btn_reset_encargado", use_container_width=True):
                    st.session_state.reset_firma_encargado_hpt += 1
                    st.rerun()

        datos_paso_actual = {"tc_nombre": tc_nombre, "tc_fecha": tc_fecha, "tc_hora": tc_hora, "tc_duracion": tc_duracion}
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("⬅️ ATRÁS", key="back4", use_container_width=True):
                st.session_state.hpt_data.update(datos_paso_actual)
                set_step(1 if st.session_state.hpt_data.get("condicion_puerto") == "Cerrado total" else 3)
                st.rerun()
        with col_btn2:
            if st.button("GENERAR Y ALMACENAR HPT", type="primary", use_container_width=True):
                st.session_state.hpt_data.update(datos_paso_actual)
                data = st.session_state.hpt_data
                barra_carga = st.progress(0, text="⚙️ Generando PDF...")
                try:
                    pdf = FPDF()
                    pdf.add_page()
                    logo_pdf = obtener_ruta_logo()
                    if logo_pdf and os.path.exists(logo_pdf):
                        try:
                            pdf.image(logo_pdf, x=10, y=8, h=20)
                        except Exception:
                            pass
                    pdf.set_draw_color(180, 180, 180)
                    pdf.set_y(32)
                    pdf.set_font("Arial", "B", 12)
                    pdf.set_fill_color(15, 55, 105)
                    pdf.set_text_color(255, 255, 255)
                    pdf.cell(0, 10, "HERRAMIENTA DE PREVENCION EN TERRENO (HPT) - ROV", border=0, ln=True, align="C", fill=True)

                    hora_chile = obtener_hora_chile()
                    pdf.set_font("Arial", "I", 8)
                    pdf.set_text_color(128, 128, 128)
                    pdf.cell(0, 6, limpiar_texto_pdf(f"Sello de Auditoría Inmutable: Generado el {hora_chile.strftime('%Y-%m-%d %H:%M:%S')} por {st.session_state.current_user}"), border=0, ln=True, align="C")
                    pdf.ln(2)

                    pdf.set_fill_color(15, 55, 105)
                    pdf.set_text_color(255, 255, 255)
                    pdf.set_font("Arial", "B", 9)
                    pdf.cell(190, 6, "1. DATOS OPERATIVOS", border=0, ln=True, fill=True)
                    pdf.ln(1)
                    pdf.set_text_color(0, 0, 0)

                    def row_hpt(l1, v1, l2, v2):
                        pdf.set_font("Arial", "B", 8)
                        pdf.cell(35, 6, limpiar_texto_pdf(l1), border=1)
                        pdf.set_font("Arial", "", 8)
                        pdf.cell(60, 6, limpiar_texto_pdf(str(v1)[:35]), border=1)
                        pdf.set_font("Arial", "B", 8)
                        pdf.cell(35, 6, limpiar_texto_pdf(l2), border=1)
                        pdf.set_font("Arial", "", 8)
                        pdf.cell(60, 6, limpiar_texto_pdf(str(v2)[:35]), border=1, ln=True)

                    row_hpt("Empresa / Mandante:", data.get("empresa", ""), "Centro de Cultivo:", data.get("centro", ""))
                    row_hpt("Fecha Maniobra:", data.get("fecha", ""), "Area Geografica:", data.get("area", ""))
                    row_hpt("Hora Inicio Rango:", data.get("hora_inicio", ""), "Hora Termino Rango:", data.get("hora_termino", ""))
                    row_hpt("Nombre Ponton:", data.get("ponton", ""), "Condicion Puerto:", data.get("condicion_puerto", ""))
                    row_hpt("Encargado Centro:", data.get("encargado", ""), "Correo Centro:", data.get("correo", ""))
                    row_hpt("Prevencionista 1:", data.get("prevencion_1", ""), "Prevencionista 2:", data.get("prevencion_2", ""))

                    pdf.set_font("Arial", "B", 8)
                    pdf.cell(35, 6, "Trabajo Rutinario:", border=1)
                    pdf.set_font("Arial", "", 8)
                    pdf.cell(155, 6, limpiar_texto_pdf(data.get("trabajo_rutinario", "Sí")), border=1, ln=True)

                    pdf.set_font("Arial", "B", 8)
                    pdf.set_fill_color(15, 55, 105)
                    pdf.set_text_color(255, 255, 255)
                    pdf.cell(190, 6, "Faena Primaria y Detalles Especificos:", border=0, ln=True, fill=True)
                    pdf.ln(1)
                    pdf.set_text_color(0, 0, 0)
                    pdf.set_font("Arial", "", 8)
                    pdf.multi_cell(190, 5, limpiar_texto_pdf(f"FAENA: {data.get('faena', '')}\nDETALLES: {data.get('tarea', '')}"), border=1)

                    pdf.ln(2)
                    pdf.set_fill_color(15, 55, 105)
                    pdf.set_text_color(255, 255, 255)
                    pdf.set_font("Arial", "B", 9)
                    pdf.cell(190, 6, "2. EQUIPO DE PROTECCION PERSONAL SELECCIONADO", border=0, ln=True, fill=True)
                    pdf.ln(1)
                    pdf.set_text_color(0, 0, 0)
                    pdf.set_font("Arial", "", 8)
                    epp_labels = ["Guantes", "Chaleco", "Zapatos", "Ropa Termica", "Traje Agua", "Comunicacion", "Botiquin"]
                    epp_vals = data.get("epp", [])
                    epp_sel = [epp_labels[i] for i in range(len(epp_labels)) if i < len(epp_vals) and epp_vals[i]]
                    if not epp_sel:
                        pdf.cell(190, 6, "Ningun EPP registrado o Aplica (Puerto Cerrado Total).", border=1, ln=True)
                    else:
                        for i, epp in enumerate(epp_sel):
                            pdf.cell(190 / 3, 6, f"[ X ] {epp}", border=1, ln=1 if (i + 1) % 3 == 0 or i == len(epp_sel) - 1 else 0)

                    pdf.ln(2)
                    pdf.set_fill_color(15, 55, 105)
                    pdf.set_text_color(255, 255, 255)
                    pdf.set_font("Arial", "B", 9)
                    pdf.cell(190, 6, "3. VERIFICACIONES CLAVES DE SEGURIDAD", border=0, ln=True, fill=True)
                    pdf.ln(1)
                    pdf.set_text_color(0, 0, 0)
                    pdf.set_font("Arial", "", 8)
                    for preg, resp in [
                        ("Personal instruido en Procedimiento Especifico (Charla 5 min)", data.get("check_instruido", "")),
                        ("Condiciones ambientales (viento, lluvia, oleaje) evaluadas y seguras", data.get("check_clima", "")),
                        ("Equipos de apoyo y comunicacion operativos y revisados", data.get("check_equipos", "")),
                        ("Area de trabajo ordenada, despejada y delimitada", data.get("check_orden", "")),
                    ]:
                        pdf.cell(160, 6, preg, border=1)
                        pdf.cell(30, 6, limpiar_texto_pdf(resp), border=1, align="C", ln=True)

                    pdf.ln(2)
                    pdf.set_fill_color(15, 55, 105)
                    pdf.set_text_color(255, 255, 255)
                    pdf.set_font("Arial", "B", 9)
                    pdf.cell(190, 6, "4. RIESGOS CRITICOS EVALUADOS (ERC)", border=0, ln=True, fill=True)
                    pdf.ln(1)
                    pdf.set_text_color(0, 0, 0)
                    pdf.set_font("Arial", "", 8)
                    erc_labels = ["Izaje", "Buceo", "Eq. Electricos", "Caidas", "Navegacion", "Atrapamiento"]
                    erc_vals = data.get("erc", [])
                    erc_sel = [erc_labels[i] for i in range(len(erc_labels)) if i < len(erc_vals) and erc_vals[i]]
                    if not erc_sel:
                        pdf.cell(190, 6, "Ningun Riesgo seleccionado o Aplica (Puerto Cerrado Total).", border=1, ln=True)
                    else:
                        for i, erc in enumerate(erc_sel):
                            pdf.cell(190 / 2, 6, f"[ X ] {erc}", border=1, ln=1 if (i + 1) % 2 == 0 or i == len(erc_sel) - 1 else 0)

                    pdf.ln(2)
                    pdf.set_fill_color(15, 55, 105)
                    pdf.set_text_color(255, 255, 255)
                    pdf.set_font("Arial", "B", 9)
                    pdf.cell(190, 6, "5. DIFUSION Y TOMA DE CONOCIMIENTO", border=0, ln=True, fill=True)
                    pdf.ln(1)
                    pdf.set_text_color(0, 0, 0)
                    row_hpt("Relator / Piloto:", tc_relator, "RUT Relator:", tc_rut)
                    pdf.set_font("Arial", "B", 8)
                    pdf.cell(35, 6, "Tema Difundido:", border=1)
                    pdf.set_font("Arial", "", 8)
                    pdf.cell(155, 6, limpiar_texto_pdf(tc_nombre[:80]), border=1, ln=True)
                    row_hpt("Fecha y Hora:", f"{tc_fecha} {tc_hora}", "Duracion Rango:", tc_duracion)

                    pdf.ln(2)
                    pdf.set_fill_color(15, 55, 105)
                    pdf.set_text_color(255, 255, 255)
                    pdf.set_font("Arial", "B", 9)
                    pdf.cell(190, 6, "6. CUADRO DE FIRMAS RESPONSABLES", border=0, ln=True, fill=True)
                    pdf.ln(1)
                    pdf.set_text_color(0, 0, 0)
                    pdf.cell(95, 22, "", border=1)
                    pdf.cell(95, 22, "", border=1, ln=True)
                    id_firmas = uuid.uuid4().hex[:8]
                    f_serv = f"f_serv_{id_firmas}.jpg"
                    f_enc = f"f_encargado_{id_firmas}.jpg"
                    if procesar_firma(firma_sup_serv, f_serv):
                        pdf.image(f_serv, x=35, y=pdf.get_y() - 20, w=45, h=15)
                    if procesar_firma(firma_encargado, f_enc):
                        pdf.image(f_enc, x=130, y=pdf.get_y() - 20, w=45, h=15)
                    pdf.set_font("Arial", "B", 8)
                    pdf.cell(95, 6, "Firma Supervisor Servicio", border=1, align="C")
                    pdf.cell(95, 6, "Firma Encargado de Centro", border=1, ln=True, align="C")

                    if data.get("evidencia_puerto"):
                        pdf.add_page()
                        pdf.set_draw_color(180, 180, 180)
                        pdf.set_font("Arial", "B", 10)
                        pdf.set_fill_color(15, 55, 105)
                        pdf.set_text_color(255, 255, 255)
                        pdf.cell(190, 10, "EVIDENCIA FOTOGRAFICA: ESTADO DE PUERTO", border=0, ln=True, fill=True)
                        pdf.set_text_color(0, 0, 0)
                        pdf.ln(5)
                        temp_img_path = f"temp_evidencia_{uuid.uuid4().hex[:6]}.jpg"
                        with open(temp_img_path, "wb") as f:
                            f.write(optimizar_imagen_ram(data["evidencia_puerto"]))
                        with Image.open(temp_img_path) as pil_img:
                            w_px, h_px = pil_img.size
                            aspect = h_px / w_px
                            w_mm = 160
                            h_mm = w_mm * aspect
                            if h_mm > 180:
                                h_mm = 180
                                w_mm = h_mm / aspect
                        pdf.image(temp_img_path, x=(210 - w_mm) / 2, y=pdf.get_y(), w=w_mm, h=h_mm)
                        os.remove(temp_img_path)

                    pdf.set_auto_page_break(auto=False)
                    pdf.set_y(-18)
                    pdf.set_font("Arial", "B", 8)
                    pdf.set_text_color(15, 55, 105)
                    pdf.cell(190, 4, "TECHTRIDENT - NTORRES@TECHTRIDENT.CL - WWW.TECHTRIDENT.CL", border=0, align="C", ln=1)
                    pdf.set_font("Arial", "I", 8)
                    pdf.set_text_color(128, 128, 128)
                    pdf.cell(190, 4, limpiar_texto_pdf("TechTrident 2026 ©"), border=0, align="C")

                    archivo_pdf = f"HPT_{str(data.get('centro', '')).replace(' ', '_')}_{data.get('fecha')}_{str(uuid.uuid4())[:8]}.pdf"
                    pdf.output(archivo_pdf)
                    st.session_state.hpt_pdf_generado = archivo_pdf

                    url_pdf_nube = ""
                    if supabase is not None:
                        for intento in range(3):
                            try:
                                time.sleep(0.5)
                                with open(archivo_pdf, "rb") as f:
                                    supabase.storage.from_("documentos").upload(path=archivo_pdf, file=f, file_options={"content-type": "application/pdf"})
                                url_pdf_nube = supabase.storage.from_("documentos").get_public_url(archivo_pdf)
                                break
                            except Exception as upload_error:
                                if intento == 2:
                                    st.warning(f"⚠️ Error al subir PDF: {upload_error}")
                                time.sleep(1)

                    row_data = {
                        "fecha": str(data.get("fecha")), "usuario": st.session_state.current_user,
                        "empresa": data.get("empresa"), "centro": data.get("centro"), "area": data.get("area"),
                        "ponton": data.get("ponton"), "condicion_puerto": data.get("condicion_puerto"),
                        "hora_inicio": data.get("hora_inicio"), "hora_termino": data.get("hora_termino"),
                        "faena": data.get("faena"), "tarea": data.get("tarea"), "url_documento": url_pdf_nube
                    }
                    try:
                        if supabase is not None:
                            supabase.table("hpt_history").insert(row_data).execute()
                        else:
                            st.session_state.local_hpt_history.append(row_data)
                    except Exception as db_err:
                        st.warning(f"⚠️ Guardado local (BD: {db_err})")
                        st.session_state.local_hpt_history.append(row_data)

                    eliminar_borrador_usuario(st.session_state.current_user)
                    if os.path.exists(f_serv):
                        os.remove(f_serv)
                    if os.path.exists(f_enc):
                        os.remove(f_enc)

                    barra_carga.progress(100, text="✅ ¡LISTO!")
                    time.sleep(0.5)
                    barra_carga.empty()
                except Exception as e:
                    barra_carga.empty()
                    st.error(f"Falla: {e}")

        if st.session_state.hpt_pdf_generado and os.path.exists(st.session_state.hpt_pdf_generado):
            st.success("✅ HPT Generada y Guardada con éxito.")
            with open(st.session_state.hpt_pdf_generado, "rb") as pdf_file:
                st.download_button(
                    label="📥 Descargar Copia Local PDF",
                    data=pdf_file,
                    file_name=st.session_state.hpt_pdf_generado,
                    mime="application/pdf",
                    use_container_width=True
                )

    with barra_superior:
        col_top1, col_top2 = st.columns([2, 1])
        with col_top1:
            st.button("⬅️ Cancelar y Volver al Menú HPT", on_click=set_page, args=("hpt_menu",), use_container_width=True)
        with col_top2:
            if st.button("💾 GUARDAR BORRADOR", use_container_width=True):
                st.session_state.hpt_data.update(datos_paso_actual)
                guardar_borrador_usuario(st.session_state.current_user, st.session_state.hpt_step, st.session_state.hpt_data)
                st.success("✅ Avance guardado en borrador.")
                time.sleep(1.0)
                set_page("hpt_menu")
                st.rerun()

# ------------------------------------------------------------------------------
# MÓDULO: REPORTE DIARIO (SUITE COMPLETA)
# ------------------------------------------------------------------------------
elif st.session_state.current_page == "reporte_diario":
    render_barra_superior_admin()
    st.button("⬅️ Volver al Menú Principal", on_click=set_page, args=("main_menu",))
    st.markdown("<h1 style='text-align: center;'>🚢 Reporte Diario Operativo</h1>", unsafe_allow_html=True)
    st.divider()

    col_em1, col_em2 = st.columns(2)
    with col_em1:
        empresa_rd = st.selectbox("Empresa / Mandante", ["Salmones Blumar", "Salmones Blumar Magallanes"])
    with col_em2:
        opciones_centros = list(st.session_state.db_centros_areas.keys())
        centro_rd = st.selectbox("Centro de Cultivo", opciones_centros)

    area_rd = st.session_state.db_centros_areas.get(centro_rd, "Desconocida")
    correo_asignado_rd = st.session_state.db_centros_correos.get(centro_rd, "sin_correo@blumar.com")
    st.info(f"⚓ Área Asignada: **{area_rd}** | 📬 Correo Central: **{correo_asignado_rd}**")
    estado_turno = st.radio("Estado Operativo del Piloto", ["Operativo (Faena Normal)", "Detenido por Salud / Licencia"], horizontal=True)

    col1, col2 = st.columns(2)
    with col1:
        fecha_rd = st.date_input("Fecha", value=obtener_hora_chile().date())
        piloto_rd = st.text_input("Nombre de Piloto", value=st.session_state.get("rd_piloto", st.session_state.current_user), key="rd_piloto")
        encargado_rd = st.text_input("Encargado de Centro", key="rd_encargado")
        condicion_puerto_rd = st.selectbox("Condición de Puerto", ["Abierto", "Cerrado para naves menores", "Cerrado total"], key="rd_puerto")
        st.link_button("🌐 Revisar SITPORT (Directemar)", "https://sitport.directemar.cl/#/general", use_container_width=True)
        evidencia_img_rd = None
        if condicion_puerto_rd in ["Cerrado para naves menores", "Cerrado total"]:
            evidencia_img_rd = st.file_uploader("📸 Evidencia fotográfica de puerto cerrado", type=["png", "jpg", "jpeg"], key="rd_evidencia")
        ponton_rd = st.text_input("Nombre Pontón", key="rd_ponton")

    if estado_turno != "Operativo (Faena Normal)" or condicion_puerto_rd == "Cerrado total":
        st.warning("⚠️ **Modo Express Activado:** Sin operaciones submarinas.")
        with col2:
            st.text_input("Jaula / Balsa", value="N/A (Sin operaciones)", disabled=True)
            st.text_input("Rango Horario", value="N/A", disabled=True)
        jaula_rd, hora_inicio_rd, hora_termino_rd = "N/A", "08:00", "18:00"
        motivo = "Condición de Puerto Cerrado Total" if condicion_puerto_rd == "Cerrado total" else estado_turno
        tarea_rd = f"Jornada sin operaciones submarinas. Motivo de inactividad: {motivo}."
    else:
        with col2:
            jaula_rd = st.text_input("Jaula / Balsa Trabajada", key="rd_jaula")
            hora_inicio_rd = st.selectbox("Hora Inicio Rango", RANGOS_INICIO, key="rd_hora_inicio")
            hora_termino_rd = st.selectbox("Hora Término Rango", RANGO_TERMINO, key="rd_hora_termino")
        tarea_rd = st.text_area("Descripción de la Tarea Realizada", key="rd_tarea")

    st.subheader("Firmas de Responsabilidad")
    col_f_rd1, col_f_rd2 = st.columns(2)
    with col_f_rd1:
        st.write("Firma Piloto ROV")
        firma_piloto_rd = crear_canvas_firma(stroke_width=2, stroke_color="#000", background_color="#FFF", height=150, width=300, key="firma_p_rd")
    with col_f_rd2:
        st.write("Firma Encargado de Centro")
        firma_encargado_rd = crear_canvas_firma(stroke_width=2, stroke_color="#000", background_color="#FFF", height=150, width=300, key="firma_e_rd")

    if st.button("GENERAR Y GUARDAR REPORTE DIARIO", type="primary", use_container_width=True):
        barra_rd = st.progress(0, text="⚙️ Generando PDF...")
        hora_chile = obtener_hora_chile()
        try:
            if supabase is not None:
                res_count = supabase.table("reportes_history").select("id", count="exact").execute()
                correlativo = (res_count.count or 0) + 1
            else:
                correlativo = len(st.session_state.local_reportes_history) + 1
        except Exception:
            correlativo = len(st.session_state.local_reportes_history) + 1
        folio_str = f"RD-{hora_chile.strftime('%Y%m%d')}-{correlativo:03d}-{hora_chile.strftime('%H%M')}"

        try:
            pdf_rd = FPDF()
            pdf_rd.add_page()
            pdf_rd.set_draw_color(180, 180, 180)
            logo_pdf_rd = obtener_ruta_logo()
            if logo_pdf_rd and os.path.exists(logo_pdf_rd):
                try:
                    pdf_rd.image(logo_pdf_rd, x=10, y=8, h=20)
                except Exception:
                    pass
            pdf_rd.set_y(32)
            pdf_rd.set_font("Arial", "B", 14)
            pdf_rd.set_fill_color(15, 55, 105)
            pdf_rd.set_text_color(255, 255, 255)
            pdf_rd.cell(0, 10, "REPORTE DIARIO DE OPERACIONES - ROV", border=0, ln=True, align="C", fill=True)
            pdf_rd.set_font("Arial", "I", 9)
            pdf_rd.set_text_color(128, 128, 128)
            pdf_rd.cell(0, 8, limpiar_texto_pdf(f"Folio: {folio_str} | Generado el {hora_chile.strftime('%Y-%m-%d %H:%M:%S')} por {piloto_rd}"), border=0, ln=True, align="C")
            pdf_rd.set_font("Arial", "B", 12)
            pdf_rd.set_text_color(15, 55, 105)
            pdf_rd.cell(0, 6, limpiar_texto_pdf(f"N° {correlativo}"), border=0, ln=True, align="C")
            pdf_rd.ln(5)

            pdf_rd.set_fill_color(15, 55, 105)
            pdf_rd.set_text_color(255, 255, 255)
            pdf_rd.set_font("Arial", "B", 10)
            pdf_rd.cell(190, 8, "1. DATOS GENERALES", border=0, ln=True, fill=True)
            pdf_rd.ln(2)
            pdf_rd.set_text_color(0, 0, 0)

            def row_rd(l1, v1, l2, v2):
                pdf_rd.set_font("Arial", "B", 9)
                pdf_rd.cell(35, 8, limpiar_texto_pdf(l1), border=1)
                pdf_rd.set_font("Arial", "", 9)
                pdf_rd.cell(60, 8, limpiar_texto_pdf(str(v1)[:35]), border=1)
                pdf_rd.set_font("Arial", "B", 9)
                pdf_rd.cell(35, 8, limpiar_texto_pdf(l2), border=1)
                pdf_rd.set_font("Arial", "", 9)
                pdf_rd.cell(60, 8, limpiar_texto_pdf(str(v2)[:35]), border=1, ln=True)

            row_rd("Fecha:", fecha_rd, "Rango Horario:", f"{hora_inicio_rd} - {hora_termino_rd}")
            row_rd("Piloto ROV:", piloto_rd, "Nombre Ponton:", ponton_rd)
            row_rd("Empresa:", empresa_rd, "Centro Cultivo:", centro_rd)
            row_rd("Encargado Centro:", encargado_rd or "N/A", "Correo Centro:", correo_asignado_rd)
            row_rd("Area Asignada:", area_rd, "Cond. Puerto:", condicion_puerto_rd)

            pdf_rd.ln(6)
            pdf_rd.set_fill_color(15, 55, 105)
            pdf_rd.set_text_color(255, 255, 255)
            pdf_rd.set_font("Arial", "B", 10)
            pdf_rd.cell(190, 8, "2. DETALLE OPERATIVO", border=0, ln=True, fill=True)
            pdf_rd.ln(2)
            pdf_rd.set_fill_color(240, 240, 240)
            pdf_rd.set_text_color(0, 0, 0)
            pdf_rd.set_font("Arial", "B", 9)
            pdf_rd.cell(190, 8, "Estructura Intervenida:", border=1, ln=True, fill=True)
            pdf_rd.set_font("Arial", "", 9)
            pdf_rd.cell(190, 8, limpiar_texto_pdf(jaula_rd), border=1, ln=True)

            pdf_rd.ln(4)
            pdf_rd.set_fill_color(15, 55, 105)
            pdf_rd.set_text_color(255, 255, 255)
            pdf_rd.set_font("Arial", "B", 10)
            pdf_rd.cell(190, 8, "Descripcion de la Tarea Realizada:", border=0, ln=True, fill=True)
            pdf_rd.ln(2)
            pdf_rd.set_text_color(0, 0, 0)
            pdf_rd.set_font("Arial", "", 9)
            x_s, y_s = pdf_rd.get_x(), pdf_rd.get_y()
            pdf_rd.multi_cell(190, 6, txt=limpiar_texto_pdf(tarea_rd), border=0)
            h_box = max(pdf_rd.get_y() - y_s, 25)
            pdf_rd.set_xy(x_s, y_s)
            pdf_rd.cell(190, h_box, "", border=1, ln=True)
            pdf_rd.set_xy(x_s, y_s + h_box)

            pdf_rd.ln(8)
            if pdf_rd.get_y() > 220:
                pdf_rd.add_page()
            pdf_rd.set_fill_color(15, 55, 105)
            pdf_rd.set_text_color(255, 255, 255)
            pdf_rd.set_font("Arial", "B", 10)
            pdf_rd.cell(190, 8, "3. CUADRO DE FIRMAS RESPONSABLES", border=0, ln=True, fill=True)
            pdf_rd.ln(2)
            pdf_rd.set_text_color(0, 0, 0)
            pdf_rd.cell(95, 25, "", border=1)
            pdf_rd.cell(95, 25, "", border=1, ln=True)
            id_f_rd = uuid.uuid4().hex[:8]
            f_pil_rd = f"f_p_rd_{id_f_rd}.jpg"
            f_enc_rd = f"f_e_rd_{id_f_rd}.jpg"
            if procesar_firma(firma_piloto_rd, f_pil_rd):
                pdf_rd.image(f_pil_rd, x=35, y=pdf_rd.get_y() - 22, w=45, h=18)
            if procesar_firma(firma_encargado_rd, f_enc_rd):
                pdf_rd.image(f_enc_rd, x=130, y=pdf_rd.get_y() - 22, w=45, h=18)
            pdf_rd.set_font("Arial", "B", 9)
            pdf_rd.cell(95, 8, "Firma Piloto ROV", border=1, align="C")
            pdf_rd.cell(95, 8, "Firma Encargado de Centro", border=1, ln=True, align="C")

            if evidencia_img_rd:
                pdf_rd.add_page()
                pdf_rd.set_font("Arial", "B", 10)
                pdf_rd.set_fill_color(15, 55, 105)
                pdf_rd.set_text_color(255, 255, 255)
                pdf_rd.cell(190, 10, "EVIDENCIA FOTOGRAFICA: ESTADO DE PUERTO", border=0, ln=True, fill=True)
                pdf_rd.set_text_color(0, 0, 0)
                pdf_rd.ln(5)
                temp_img_path = f"temp_evidencia_rd_{uuid.uuid4().hex[:6]}.jpg"
                with open(temp_img_path, "wb") as f:
                    f.write(optimizar_imagen_ram(evidencia_img_rd.getvalue()))
                with Image.open(temp_img_path) as pil_img:
                    w_px, h_px = pil_img.size
                    aspect = h_px / w_px
                    w_mm = 160
                    h_mm = w_mm * aspect
                    if h_mm > 180:
                        h_mm = 180
                        w_mm = h_mm / aspect
                pdf_rd.image(temp_img_path, x=(210 - w_mm) / 2, y=pdf_rd.get_y(), w=w_mm, h=h_mm)
                os.remove(temp_img_path)

            pdf_rd.set_auto_page_break(auto=False)
            pdf_rd.set_y(-18)
            pdf_rd.set_font("Arial", "B", 8)
            pdf_rd.set_text_color(15, 55, 105)
            pdf_rd.cell(190, 4, "TECHTRIDENT - NTORRES@TECHTRIDENT.CL - WWW.TECHTRIDENT.CL", border=0, align="C", ln=1)
            pdf_rd.set_font("Arial", "I", 8)
            pdf_rd.set_text_color(128, 128, 128)
            pdf_rd.cell(190, 4, limpiar_texto_pdf("TechTrident 2026 ©"), border=0, align="C")

            archivo_pdf_rd = f"Reporte_Diario_{centro_rd.replace(' ', '_')}_{fecha_rd}_{str(uuid.uuid4())[:8]}.pdf"
            pdf_rd.output(archivo_pdf_rd)
            st.session_state.rd_pdf_generado = archivo_pdf_rd

            url_pdf_rd_nube = ""
            if supabase is not None:
                for intento in range(3):
                    try:
                        time.sleep(0.5)
                        with open(archivo_pdf_rd, "rb") as f:
                            supabase.storage.from_("documentos").upload(path=archivo_pdf_rd, file=f, file_options={"content-type": "application/pdf"})
                        url_pdf_rd_nube = supabase.storage.from_("documentos").get_public_url(archivo_pdf_rd)
                        break
                    except Exception:
                        time.sleep(1)

            datos_rd = {
                "fecha": str(fecha_rd), "usuario": piloto_rd, "centro": centro_rd, "area": area_rd,
                "jaula": str(jaula_rd), "ponton": ponton_rd, "hora_inicio": str(hora_inicio_rd),
                "hora_termino": str(hora_termino_rd), "condicion_puerto": condicion_puerto_rd,
                "tarea": tarea_rd, "url_documento": url_pdf_rd_nube,
                "empresa": empresa_rd, "folio": folio_str, "encargado": encargado_rd
            }
            try:
                if supabase is not None:
                    supabase.table("reportes_history").insert(datos_rd).execute()
                else:
                    st.session_state.local_reportes_history.append(datos_rd)
            except Exception:
                st.session_state.local_reportes_history.append(datos_rd)

            if os.path.exists(f_pil_rd):
                os.remove(f_pil_rd)
            if os.path.exists(f_enc_rd):
                os.remove(f_enc_rd)
            barra_rd.progress(100, text="✅ ¡LISTO!")
            time.sleep(0.5)
            barra_rd.empty()
        except Exception as e:
            barra_rd.empty()
            st.error(f"Error técnico: {e}")

    if st.session_state.rd_pdf_generado and os.path.exists(st.session_state.rd_pdf_generado):
        st.success("✅ Reporte Diario Generado y guardado.")
        with open(st.session_state.rd_pdf_generado, "rb") as pdf_file:
            st.download_button(
                label="📥 Descargar PDF", data=pdf_file,
                file_name=st.session_state.rd_pdf_generado, mime="application/pdf", use_container_width=True
            )

# ------------------------------------------------------------------------------
# MÓDULO: HISTORIAL GLOBAL / AUDITORÍA (SUITE COMPLETA)
# ------------------------------------------------------------------------------
elif st.session_state.current_page == "modulo_busqueda":
    render_barra_superior_admin()
    st.button("⬅️ Volver al Menú Principal", on_click=set_page, args=("main_menu",))
    st.markdown("<h1 style='text-align: center;'>📊 Historial de Documentación y Descargas</h1>", unsafe_allow_html=True)
    st.divider()

    col_rol, col_modulo = st.columns(2)
    with col_rol:
        idx_rol = 1 if es_administrador() else 0
        rol_busqueda = st.radio("Seleccione Perfil de Búsqueda", ["Usuario Común", "Administrador"], index=idx_rol)
    with col_modulo:
        modulo_consulta = st.selectbox("Módulo a Consultar", ["Entregas de Turno", "HPT", "Reportes Diarios"])

    tabla_map = {"HPT": "hpt_history", "Reportes Diarios": "reportes_history", "Entregas de Turno": "entrega_history"}
    tabla_actual = tabla_map[modulo_consulta]
    registros_hist = []

    if rol_busqueda == "Administrador":
        admin_autorizado = st.session_state.admin_acceso_historial or es_administrador()
        if not admin_autorizado:
            clave_ingresada = st.text_input("Ingrese Pin de Seguridad Administrador", type="password")
            if st.button("Ingresar"):
                if clave_ingresada == CLAVE_ADMIN:
                    st.session_state.admin_acceso_historial = True
                    st.rerun()
                else:
                    st.error("Código de seguridad incorrecto.")
        else:
            st.success("Acceso Gerencial Desbloqueado.")
            if modulo_consulta == "Entregas de Turno":
                registros_hist = obtener_todas_las_entregas(incluir_demo=st.session_state.usar_datos_demo)
            else:
                try:
                    res = supabase.table(tabla_actual).select("*").order("id", desc=True).execute()
                    registros_hist = res.data or []
                except Exception:
                    registros_hist = st.session_state.local_hpt_history if modulo_consulta == "HPT" else st.session_state.local_reportes_history
    else:
        user_actual = st.session_state.current_user
        st.info(f"Mostrando registros del Piloto: **{user_actual}**")
        if modulo_consulta == "Entregas de Turno":
            registros_hist = [r for r in obtener_todas_las_entregas(incluir_demo=False) if r.get("usuario") == user_actual]
        else:
            try:
                res = supabase.table(tabla_actual).select("*").filter("usuario", "eq", user_actual).order("id", desc=True).execute()
                registros_hist = res.data or []
            except Exception:
                base_l = st.session_state.local_hpt_history if modulo_consulta == "HPT" else st.session_state.local_reportes_history
                registros_hist = [r for r in base_l if r.get("usuario") == user_actual]

    if (rol_busqueda == "Usuario Común") or (rol_busqueda == "Administrador" and (st.session_state.admin_acceso_historial or es_administrador())):
        if registros_hist:
            df = limpiar_df_vista(pd.DataFrame(registros_hist))
            if modulo_consulta == "HPT":
                cols_m = ["fecha", "usuario", "centro", "area", "ponton", "condicion_puerto", "url_documento"]
            elif modulo_consulta == "Reportes Diarios":
                cols_m = ["fecha", "usuario", "centro", "area", "jaula", "tarea", "url_documento"]
            else:
                cols_m = ["fecha", "usuario", "piloto_entrante", "centro", "area", "rov_en_uso", "rov_con_falla", "estado_rov", "url_documento"]
            cols_m = [c for c in cols_m if c in df.columns]
            st.dataframe(
                df[cols_m],
                column_config={"url_documento": st.column_config.LinkColumn("Enlace PDF", display_text="📥 Descargar PDF")},
                use_container_width=True
            )
        else:
            st.info(f"No se registran datos en el historial de {modulo_consulta}.")

# ------------------------------------------------------------------------------
# MÓDULO: PANEL GRÁFICOS HPT (SUITE COMPLETA)
# ------------------------------------------------------------------------------
elif st.session_state.current_page == "panel_graficos":
    render_barra_superior_admin()
    st.button("⬅️ Volver al Menú Principal", on_click=set_page, args=("main_menu",))
    st.markdown("<h1 style='text-align: center;'>📈 Métricas HPT e Inteligencia de Negocio</h1>", unsafe_allow_html=True)
    st.divider()

    admin_autorizado_graf = st.session_state.admin_acceso_graficos or es_administrador()
    if not admin_autorizado_graf:
        clave_dash = st.text_input("Autenticación Gerencial (Pin)", type="password", key="dash_pin")
        if st.button("Ingresar"):
            if clave_dash == CLAVE_ADMIN:
                st.session_state.admin_acceso_graficos = True
                st.rerun()
            else:
                st.error("Código inválido.")
    else:
        try:
            res_hpt = supabase.table("hpt_history").select("*").execute()
            df_hpt = pd.DataFrame(res_hpt.data)
        except Exception:
            df_hpt = pd.DataFrame(st.session_state.local_hpt_history)

        if not df_hpt.empty:
            c_g1, c_g2 = st.columns(2)
            with c_g1:
                st.subheader("📊 Operaciones por Centro")
                st.bar_chart(df_hpt["centro"].value_counts())
                st.subheader("⚠️ Puertos Cerrados por Área")
                df_cerr = df_hpt[df_hpt["condicion_puerto"] != "Abierto"]
                if not df_cerr.empty:
                    st.bar_chart(df_cerr["area"].value_counts(), color="#ff4b4b")
                else:
                    st.info("Ningún registro de puerto cerrado.")
            with c_g2:
                st.subheader("🛠️ Top Faenas más Realizadas")
                if "faena" in df_hpt.columns:
                    st.bar_chart(df_hpt["faena"].value_counts(), color="#00ff99")
                st.subheader("💼 Distribución por Piloto ROV")
                st.bar_chart(df_hpt["usuario"].value_counts(), color="#f5b841")
        else:
            st.info("No existen suficientes registros HPT para estructurar gráficos.")
