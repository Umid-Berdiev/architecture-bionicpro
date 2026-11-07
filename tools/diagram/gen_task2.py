"""Build the Task 2 diagram from the Task 1 to-be diagram.

Page 1 ("C4 Container (to-be)") gets the reporting pipeline: Airflow (ETL), the ClickHouse OLAP
mart, the extraction flows from the CRM and telemetry databases and the read path of the API.
Page 2 ("ETL и витрина") shows the DAG tasks, the ClickHouse tables with their keys, the watermark
and how the reports API queries the mart. The token-flow page of Task 1 is not repeated here.

Usage: python3 tools/diagram/gen_task2.py "Task1/BionicPRO_C4_container-diagram_to-be.drawio" \
                                          "Task2/BionicPRO_C4_container-diagram_to-be.drawio"
"""
import sys
import xml.etree.ElementTree as ET

SRC, OUT = sys.argv[1], sys.argv[2]

tree = ET.parse(SRC)
mxfile = tree.getroot()
pages = mxfile.findall("diagram")
page1 = pages[0]
for extra in pages[1:]:          # token flow lives in Task 1
    mxfile.remove(extra)
root1 = page1.find("mxGraphModel/root")

# ---------------------------------------------------------------- lookup by C4 name / note text
by_name = {el.get("c4Name"): el for el in root1 if el.get("c4Name")}
notes = [el for el in root1 if el.tag == "mxCell" and (el.get("value") or "").startswith("<b>Обозначения</b>")]


def cell_of(obj):
    return obj if obj.tag == "mxCell" else obj.find("mxCell")


def geom_of(obj):
    return cell_of(obj).find("mxGeometry")


def move(obj, x=None, y=None, w=None, h=None):
    g = geom_of(obj)
    for k, v in (("x", x), ("y", y), ("width", w), ("height", h)):
        if v is not None:
            g.set(k, str(v))


# Styles and label templates are taken from the existing elements so the notation stays uniform.
CONTAINER_STYLE = cell_of(by_name["API"]).get("style")
DB_STYLE = cell_of(by_name["База данных"]).get("style")
BOUNDARY_STYLE = cell_of(by_name["BionicPRO"]).get("style")
CONTAINER_LABEL = by_name["API"].get("label")
DB_LABEL = by_name["База данных"].get("label")
BOUNDARY_LABEL = by_name["BionicPRO"].get("label")
TASK_STYLE = CONTAINER_STYLE.replace("fillColor=#23A2D9", "fillColor=#438DD5").replace("strokeColor=#0E7DAD", "strokeColor=#3C7FC0")
REL_STYLE = ("endArrow=blockThin;html=1;fontSize=10;fontColor=#404040;strokeWidth=1;endFill=1;"
             "strokeColor=#828282;elbow=vertical;metaEdit=1;endSize=14;startSize=14;jumpStyle=arc;"
             "jumpSize=16;rounded=0;")
REL_LABEL = ('<div style="text-align: left"><div style="text-align: center"><b>%c4Description%</b></div>'
             '<div style="text-align: center">[%c4Technology%]</div></div>')
NEW_STYLE = "strokeColor=#B85450;fontColor=#B85450;"
ETL_STYLE = "strokeColor=#2E7D32;fontColor=#2E7D32;dashed=1;dashPattern=6 4;"   # batch data movement

_n = 0


def new_id():
    global _n
    _n += 1
    return f"task2-{_n}"


def add_vertex(root, style, label_tpl, x, y, w, h, **c4):
    obj = ET.SubElement(root, "object", placeholders="1", id=new_id())
    for k, v in c4.items():
        obj.set(k, v)
    obj.set("label", label_tpl)
    c = ET.SubElement(obj, "mxCell", style=style, vertex="1", parent="1")
    g = ET.SubElement(c, "mxGeometry", x=str(x), y=str(y), width=str(w), height=str(h))
    g.set("as", "geometry")
    return obj.get("id")


def add_container(root, name, tech, desc, x, y, w=240, h=120, style=CONTAINER_STYLE):
    return add_vertex(root, style, CONTAINER_LABEL, x, y, w, h,
                      c4Name=name, c4Type="Container", c4Technology=tech, c4Description=desc)


def add_db(root, name, tech, desc, x, y, w=240, h=120):
    return add_vertex(root, DB_STYLE, DB_LABEL, x, y, w, h,
                      c4Name=name, c4Type="Container", c4Technology=tech, c4Description=desc)


def add_boundary(root, name, kind, x, y, w, h):
    return add_vertex(root, BOUNDARY_STYLE, BOUNDARY_LABEL, x, y, w, h,
                      c4Name=name, c4Type="SystemScopeBoundary", c4Application=kind)


def add_rel(root, src, dst, desc, tech, style=NEW_STYLE, exit=None, entry=None, points=None, lx=None, ly=None):
    # Endpoints may be ids of new elements or the existing <object> elements themselves.
    src = src if isinstance(src, str) else src.get("id")
    dst = dst if isinstance(dst, str) else dst.get("id")
    obj = ET.SubElement(root, "object", placeholders="1", id=new_id())
    obj.set("c4Type", "Relationship")
    obj.set("c4Technology", tech)
    obj.set("c4Description", desc)
    obj.set("label", REL_LABEL)
    st = REL_STYLE + style
    if exit:
        st += f"exitX={exit[0]};exitY={exit[1]};exitDx=0;exitDy=0;"
    if entry:
        st += f"entryX={entry[0]};entryY={entry[1]};entryDx=0;entryDy=0;"
    c = ET.SubElement(obj, "mxCell", style=st, edge="1", parent="1", source=src, target=dst)
    g = ET.SubElement(c, "mxGeometry", width="160", relative="1")
    if lx is not None:
        g.set("x", str(lx))
    if ly is not None:
        g.set("y", str(ly))
    g.set("as", "geometry")
    if points:
        arr = ET.SubElement(g, "Array")
        arr.set("as", "points")
        for px, py in points:
            ET.SubElement(arr, "mxPoint", x=str(px), y=str(py))
    return obj.get("id")


def add_note(root, text, x, y, w, h):
    c = ET.SubElement(root, "mxCell", id=new_id(), value=text, vertex="1", parent="1",
                      style="shape=note;size=14;whiteSpace=wrap;html=1;fillColor=#fff2cc;strokeColor=#d6b656;"
                            "align=left;verticalAlign=top;spacing=8;fontSize=11;fontColor=#333333;")
    g = ET.SubElement(c, "mxGeometry", x=str(x), y=str(y), width=str(w), height=str(h))
    g.set("as", "geometry")


def add_text(root, text, x, y, w, h):
    c = ET.SubElement(root, "mxCell", id=new_id(), value=text, vertex="1", parent="1",
                      style="text;html=1;whiteSpace=wrap;align=left;verticalAlign=top;fontSize=11;fontColor=#333333;")
    g = ET.SubElement(c, "mxGeometry", x=str(x), y=str(y), width=str(w), height=str(h))
    g.set("as", "geometry")


# ================================================================ PAGE 1: add the reporting pipeline
move(by_name["BionicPRO"], w=1490)                     # room for Airflow and ClickHouse on the right
move(by_name["Оператор производства"], x=2250)
move(by_name["cli tool"], x=2150)
move(by_name["ML-инженер"], x=2170)

by_name["API"].set("c4Description",
    "REST API (resource server). GET /reports: отчёт из витрины ClickHouse за уже обработанный период; "
    "проверяет JWT (JWKS, iss, aud, роль) и отдаёт только данные владельца токена (sub)")
by_name["База данных"].set("c4Description",
    "Операционные данные: телеметрия протезов (recorded_at, жест, реакция, шум, батарея, ошибки). "
    "Источник для ETL")
by_name["CRM DB"].set("c4Description", "Клиенты, протезы, заказы. Источник для ETL")

airflow = add_container(root1, "Airflow (ETL)", "Apache Airflow, DAG bionicpro_reports_etl",
    "Раз в час (@hourly): полная загрузка клиентов и протезов из CRM, инкрементальная загрузка телеметрии, "
    "пересборка витрины за затронутые дни, публикация processed_until. Метаданные — в своей PostgreSQL",
    1800, 140, h=150)
olap = add_db(root1, "Витрина отчётности (OLAP)", "ClickHouse",
    "raw-слой: crm_customers, crm_prostheses, telemetry_raw; витрина reports_mart "
    "(пользователь × протез × день, ORDER BY idp_user_id, report_date); etl_watermark",
    1800, 780, h=150)

add_rel(root1, airflow, by_name["CRM DB"], "Извлечение клиентов и протезов\n(полная загрузка)", "SQL, раз в час",
        style=ETL_STYLE, exit=(0, 0.4), entry=(1, 0.5))
add_rel(root1, airflow, by_name["База данных"], "Извлечение телеметрии\n(инкрементально по recorded_at)",
        "SQL, раз в час", style=ETL_STYLE, exit=(0.1, 1), entry=(1, 0.25), points=[(1824, 600)], lx=-0.7)
add_rel(root1, airflow, olap, "Загрузка raw-слоя,\nсборка витрины,\nзапись processed_until", "HTTP 8123, INSERT",
        style=ETL_STYLE, exit=(0.75, 1), entry=(0.75, 0), lx=-0.5)
add_rel(root1, by_name["API"], olap, "Чтение витрины по sub\nза обработанный период", "HTTP 8123, SELECT по PK",
        exit=(0.9, 1), entry=(0.4, 0), points=[(1716, 500), (1896, 500)], lx=-0.3)

for note in notes:
    move(note, x=1660, y=1060, w=440, h=250)
    note.set("value",
        "<b>Обозначения</b><br>"
        "<font color='#B85450'>——&gt;</font> связи, добавленные в to-be (задание 1 и 2)<br>"
        "<font color='#2E7D32'>- - -&gt;</font> пакетное перемещение данных (ETL)<br>"
        "——&gt; связи из as-is; серый блок — внешняя система<br><br>"
        "<b>Ключевые решения</b><br>"
        "1. Контур доступа на страну: Keycloak, BFF, Redis и БД — в стране, учётные данные из местного каталога.<br>"
        "2. Токены IdP не покидают сервер: клиенту — только session id (BFF).<br>"
        "3. Новые страны и IdP — через Identity Brokering, без изменения приложений.<br>"
        "4. Отчёты читаются из готовой витрины в ClickHouse, а не считаются на лету; "
        "витрину раз в час собирает Airflow из CRM и телеметрии.<br>"
        "5. API отдаёт только данные владельца токена и только за период до processed_until.")

# ================================================================ PAGE 2: ETL pipeline and the mart
page2 = ET.SubElement(mxfile, "diagram", name="ETL и витрина", id="task2-etl")
model2 = ET.SubElement(page2, "mxGraphModel", dx="1400", dy="900", grid="1", gridSize="10", guides="1",
                       tooltips="1", connect="1", arrows="1", fold="1", page="1", pageScale="1",
                       pageWidth="1654", pageHeight="1169", math="0", shadow="0")
root2 = ET.SubElement(model2, "root")
ET.SubElement(root2, "mxCell", id="0")
ET.SubElement(root2, "mxCell", id="1", parent="0")

# -- sources
crm_db = add_db(root2, "crm_db", "PostgreSQL, эмуляция CRM",
                "customers (idp_user_id = sub), prostheses (serial_number)", 20, 95, 200, 120)
tel_db = add_db(root2, "telemetry_db", "PostgreSQL",
                "telemetry: prosthesis_serial, recorded_at, gesture, reaction_ms, myo_noise_level, battery_pct, error_code",
                20, 305, 200, 130)
sim = add_container(root2, "telemetry_simulator", "Python",
                    "Имитирует чипы протезов: по одному чтению на протез каждые 10 с", 20, 520, 200, 100)

# -- Airflow DAG
add_boundary(root2, "Airflow · DAG bionicpro_reports_etl",
             "schedule=@hourly, catchup=false, max_active_runs=1, retries=2", 360, 40, 300, 850)
t_crm = add_container(root2, "extract_crm", "PythonOperator / TaskFlow",
                      "Полная загрузка customers и prostheses (loaded_at = now)", 390, 100, 240, 110, TASK_STYLE)
t_tel = add_container(root2, "extract_telemetry", "TaskFlow",
                      "recorded_at > max(telemetry_raw) и ≤ data_interval_end; XCom: rows, from_date, to_date",
                      390, 310, 240, 120, TASK_STYLE)
t_mart = add_container(root2, "build_mart", "TaskFlow",
                       "INSERT … SELECT за дни [from_date; to_date]; при rows = 0 — пропуск", 390, 500, 240, 110, TASK_STYLE)
t_wm = add_container(root2, "update_watermark", "TaskFlow",
                     "processed_until = data_interval_end, dag_run_id", 390, 690, 240, 100, TASK_STYLE)

# -- ClickHouse
add_boundary(root2, "ClickHouse · база reports", "OLAP", 780, 40, 580, 850)
ch_cust = add_db(root2, "crm_customers", "ReplacingMergeTree(loaded_at)", "ORDER BY customer_id", 810, 70, 240, 90)
ch_pro = add_db(root2, "crm_prostheses", "ReplacingMergeTree(loaded_at)", "ORDER BY prosthesis_id", 810, 185, 240, 90)
ch_raw = add_db(root2, "telemetry_raw", "ReplacingMergeTree",
                "PARTITION BY toYYYYMM(recorded_at), ORDER BY (prosthesis_serial, recorded_at, telemetry_id)",
                810, 310, 240, 110)
ch_mart = add_db(root2, "reports_mart", "ReplacingMergeTree(built_at)",
                 "Зерно: idp_user_id × report_date × prosthesis_serial. ORDER BY (idp_user_id, report_date, "
                 "prosthesis_serial) — запрос «пользователь за период» = один диапазон первичного ключа. "
                 "Колонки: actions_count, avg/p95/max_reaction_ms, slow_actions_count (>100 мс), avg_noise_level, "
                 "avg/min_battery_pct, error_count, active_hours, gestures Map, username, full_name, model, side",
                 810, 480, 520, 150)
ch_wm = add_db(root2, "etl_watermark", "ReplacingMergeTree(updated_at)",
               "pipeline → processed_until, dag_run_id", 810, 690, 240, 100)
add_text(root2,
         "<b>build_mart</b>: telemetry_raw ⋈ crm_prostheses FINAL ⋈ crm_customers FINAL, "
         "GROUP BY idp_user_id, toDate(recorded_at), serial — только за дни, в которые пришла новая телеметрия; "
         "старые строки вытесняются по built_at",
         1070, 320, 270, 120)

# -- consumers
api = add_container(root2, "reports-api", "Python, FastAPI",
                    "GET /reports: JWT (JWKS, iss, aud=reports-api, роль prothetic_user); user = sub; "
                    "период ограничен processed_until", 1520, 480, 240, 150)
spa = add_container(root2, "Веб-приложение", "React SPA",
                    "Кнопки «Get Report» и «Download CSV»", 1520, 700, 240, 90)

add_note(root2,
         "<b>Правила отчёта</b><br>"
         "• Отчёт никогда не считается на лету: только SELECT из reports_mart по первичному ключу.<br>"
         "• processed_until из etl_watermark — граница доступных данных. Запрошенный конец позже границы → "
         "период обрезается, в ответе clamped = true; начало позже границы → 422 с data_processed_until.<br>"
         "• День границы помечается partial = true, если ETL прошёл не в конце дня.<br>"
         "• Без дат — последние 7 обработанных дней.<br>"
         "• user_id в запросе, отличный от sub токена → 403; витрина при этом не читается.<br>"
         "• Без токена / с неверной подписью, iss, aud, exp → 401; без роли prothetic_user → 403.",
         1520, 40, 420, 300)

# -- relationships
add_rel(root2, crm_db, t_crm, "SELECT customers,\nprostheses", "SQL", style=ETL_STYLE, exit=(1, 0.5), entry=(0, 0.5))
add_rel(root2, tel_db, t_tel, "SELECT новых строк:\n(max в OLAP; data_interval_end]", "SQL", style=ETL_STYLE,
        exit=(1, 0.5), entry=(0, 0.5))
add_rel(root2, sim, tel_db, "INSERT каждые 10 с", "SQL", style="", exit=(0.5, 0), entry=(0.5, 1))

add_rel(root2, t_crm, t_tel, "", "XCom", style="", exit=(0.5, 1), entry=(0.5, 0))
add_rel(root2, t_tel, t_mart, "rows, from_date, to_date", "XCom", style="", exit=(0.5, 1), entry=(0.5, 0))
add_rel(root2, t_mart, t_wm, "", "XCom", style="", exit=(0.5, 1), entry=(0.5, 0))

add_rel(root2, t_crm, ch_cust, "INSERT", "HTTP", style=ETL_STYLE, exit=(1, 0.25), entry=(0, 0.5))
add_rel(root2, t_crm, ch_pro, "INSERT", "HTTP", style=ETL_STYLE, exit=(1, 0.75), entry=(0, 0.5))
add_rel(root2, t_tel, ch_raw, "INSERT пачками по 20 000", "HTTP", style=ETL_STYLE, exit=(1, 0.5), entry=(0, 0.5))
add_rel(root2, t_mart, ch_mart, "INSERT … SELECT", "HTTP", style=ETL_STYLE, exit=(1, 0.5), entry=(0, 0.5))
add_rel(root2, t_wm, ch_wm, "INSERT processed_until", "HTTP", style=ETL_STYLE, exit=(1, 0.5), entry=(0, 0.5))
add_rel(root2, ch_raw, ch_mart, "", "GROUP BY", style="", exit=(0.5, 1), entry=(0.25, 0))

add_rel(root2, api, ch_mart, "SELECT … WHERE idp_user_id = {sub}\nAND report_date BETWEEN from\nAND min(to, граница)",
        "HTTP 8123", exit=(0, 0.4), entry=(1, 0.4))
add_rel(root2, api, ch_wm, "SELECT processed_until", "HTTP 8123", exit=(0, 0.9), entry=(1, 0.5), lx=0.2)
add_rel(root2, spa, api, "GET /reports?from&to&format", "HTTPS, Authorization: Bearer JWT",
        exit=(0.5, 0), entry=(0.5, 1))

tree.write(OUT, encoding="utf-8", xml_declaration=False)
print("written", OUT)
