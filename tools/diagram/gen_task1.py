"""Build the Task 1 to-be C4 container diagram from the course's as-is diagram.

Page 1 keeps every element of the as-is diagram (the API and PostgreSQL containers are only
moved to the right to make room) and adds the credential-management design:

* a per-country access contour inside BionicPRO with the BFF / auth gateway, its session
  store, the regional Keycloak and the Keycloak database;
* the external account directory and the external identity services of that country;
* the web application (personal account) that, like the mobile app, talks to the BFF only;
* a placeholder contour for the next country to show the deployment pattern.

Page 2 is a sequence diagram of the token flow through the BFF (login, API call, logout).

Usage: python3 tools/diagram/gen_task1.py "Task1/BionicPRO_C4_container-diagram_to-be.drawio"
"""
import copy
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "BionicPRO_C4_model_as-is.drawio.xml")
OUT = sys.argv[1]

A = "-s9W17W-NFw-Ta7AQgpa-"   # id prefixes used by the course diagram
B = "Lhtp9tOnbV0N8Cz71-gY-"
ID = {
    "pilot": B + "2", "chip": B + "8", "db": B + "12", "boundary": B + "13", "api": B + "17",
    "mobile": B + "20", "edge_mobile_api": A + "1", "edge_api_db": A + "4", "ml": A + "11",
    "cli": A + "13", "crm": A + "16", "crm_db": A + "17", "shop": A + "19", "buyer": A + "20",
    "operator": A + "23",
}

tree = ET.parse(SRC)
mxfile = tree.getroot()
page1 = mxfile.find("diagram")
page1.set("name", "C4 Container (to-be)")
root1 = page1.find("mxGraphModel/root")
by_id = {el.get("id"): el for el in root1}


def cell_of(obj):
    return obj if obj.tag == "mxCell" else obj.find("mxCell")


def geom_of(obj):
    return cell_of(obj).find("mxGeometry")


def move(obj_id, x=None, y=None, w=None, h=None):
    g = geom_of(by_id[obj_id])
    for k, v in (("x", x), ("y", y), ("width", w), ("height", h)):
        if v is not None:
            g.set(k, str(v))


# ---------------------------------------------------------------- templates taken from the as-is diagram
CONTAINER_STYLE = cell_of(by_id[ID["api"]]).get("style")
DB_STYLE = cell_of(by_id[ID["db"]]).get("style")
BOUNDARY_STYLE = cell_of(by_id[ID["boundary"]]).get("style")
CONTAINER_LABEL = by_id[ID["api"]].get("label")
DB_LABEL = by_id[ID["db"]].get("label")
BOUNDARY_LABEL = by_id[ID["boundary"]].get("label")
# External software systems use the standard C4 grey.
EXTERNAL_STYLE = CONTAINER_STYLE.replace("fillColor=#23A2D9", "fillColor=#8C8496").replace(
    "strokeColor=#0E7DAD", "strokeColor=#736782")
# Relationship notation of the C4 draw.io library: bold description + [technology].
REL_STYLE = ("endArrow=blockThin;html=1;fontSize=10;fontColor=#404040;strokeWidth=1;endFill=1;"
             "strokeColor=#828282;elbow=vertical;metaEdit=1;endSize=14;startSize=14;jumpStyle=arc;"
             "jumpSize=16;rounded=0;")
REL_LABEL = ('<div style="text-align: left"><div style="text-align: center"><b>%c4Description%</b></div>'
             '<div style="text-align: center">[%c4Technology%]</div></div>')
NEW_STYLE = "strokeColor=#B85450;fontColor=#B85450;"   # highlights relationships added in to-be

_n = 0


def new_id(prefix="task1"):
    global _n
    _n += 1
    return f"{prefix}-{_n}"


def add_vertex(root, style, label_tpl, x, y, w, h, **c4):
    obj = ET.SubElement(root, "object", placeholders="1", id=new_id())
    for k, v in c4.items():
        obj.set(k, v)
    obj.set("label", label_tpl)
    c = ET.SubElement(obj, "mxCell", style=style, vertex="1", parent="1")
    g = ET.SubElement(c, "mxGeometry", x=str(x), y=str(y), width=str(w), height=str(h))
    g.set("as", "geometry")
    return obj.get("id")


def add_container(root, name, tech, desc, x, y, w=240, h=120):
    return add_vertex(root, CONTAINER_STYLE, CONTAINER_LABEL, x, y, w, h,
                      c4Name=name, c4Type="Container", c4Technology=tech, c4Description=desc)


def add_db(root, name, tech, desc, x, y, w=240, h=120):
    return add_vertex(root, DB_STYLE, DB_LABEL, x, y, w, h,
                      c4Name=name, c4Type="Container", c4Technology=tech, c4Description=desc)


def add_external(root, name, tech, desc, x, y, w=240, h=120):
    return add_vertex(root, EXTERNAL_STYLE, CONTAINER_LABEL, x, y, w, h,
                      c4Name=name, c4Type="Software System", c4Technology=tech, c4Description=desc)


def add_boundary(root, name, kind, x, y, w, h):
    return add_vertex(root, BOUNDARY_STYLE, BOUNDARY_LABEL, x, y, w, h,
                      c4Name=name, c4Type="SystemScopeBoundary", c4Application=kind)


def add_rel(root, src, dst, desc, tech, exit=None, entry=None, points=None, lx=None, ly=None, new=True):
    obj = ET.SubElement(root, "object", placeholders="1", id=new_id())
    obj.set("c4Type", "Relationship")
    obj.set("c4Technology", tech)
    obj.set("c4Description", desc)
    obj.set("label", REL_LABEL)
    st = REL_STYLE + (NEW_STYLE if new else "")
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


def add_note(root, text, x, y, w, h, fill="#fff2cc", stroke="#d6b656"):
    c = ET.SubElement(root, "mxCell", id=new_id(), value=text, vertex="1", parent="1",
                      style=f"shape=note;size=14;whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};"
                            "align=left;verticalAlign=top;spacing=8;fontSize=11;fontColor=#333333;")
    g = ET.SubElement(c, "mxGeometry", x=str(x), y=str(y), width=str(w), height=str(h))
    g.set("as", "geometry")
    return c.get("id")


def add_text(root, text, x, y, w, h, style=""):
    c = ET.SubElement(root, "mxCell", id=new_id(), value=text, vertex="1", parent="1",
                      style="text;html=1;whiteSpace=wrap;align=left;verticalAlign=top;fontSize=11;"
                            "fontColor=#333333;" + style)
    g = ET.SubElement(c, "mxGeometry", x=str(x), y=str(y), width=str(w), height=str(h))
    g.set("as", "geometry")
    return c.get("id")


# ================================================================ PAGE 1: container diagram
# Make room: wider and taller system boundary, API and PostgreSQL go to the right column.
move(ID["boundary"], w=1160, h=1100)
move(ID["api"], x=1500, y=300)
move(ID["db"], x=1500, y=570)
move(ID["cli"], x=1830)
move(ID["ml"], x=1850)
move(ID["mobile"], x=300, y=640)

# The mobile app no longer calls the API directly: everything goes through the BFF.
root1.remove(by_id[ID["edge_mobile_api"]])

by_id[ID["api"]].set("c4Technology", "напр. Spring Boot")
by_id[ID["api"]].set("c4Description",
    "REST API (resource server). Проверяет JWT: подпись по JWKS Keycloak, iss/aud/exp, роли; "
    "отдаёт данные только протезов пользователя (sub)")
by_id[ID["mobile"]].set("c4Technology", "iOS, Android")
by_id[ID["mobile"]].set("c4Description",
    "Донастройка протеза. Вход и вызовы API — только через BFF; токены IdP в приложение не передаются")

# ---- per-country access contour (Russia) inside BionicPRO
contour = add_boundary(root1, "Контур страны присутствия: Россия",
                       "Deployment Node: по одному такому контуру на каждую страну", 660, 480, 740, 440)
bff = add_container(root1, "BFF / Auth Gateway", "напр. Spring Cloud Gateway + OAuth2 Client",
    "Единственный OAuth2-клиент (confidential): Authorization Code + PKCE, токены хранит на сервере, "
    "клиентам выдаёт только opaque session id в HttpOnly-cookie, проксирует запросы к API с access-токеном",
    680, 520, h=150)
kc = add_container(root1, "Keycloak (IdP страны)", "Keycloak",
    "Единая точка входа контура: OIDC-провайдер для всех приложений, User Federation к местному "
    "каталогу, Identity Brokering к местным удостоверяющим службам, RBAC (user, administrator, "
    "prothetic_user)", 1140, 520, h=150)
kc_db = add_db(root1, "БД Keycloak", "PostgreSQL",
    "Realm, клиенты, роли, сессии, ссылки на федеративные учётные записи. Размещена в стране контура",
    1140, 740)
sessions = add_db(root1, "Хранилище сессий", "Redis",
    "session id → access / refresh / id token; TTL = срок жизни refresh-токена", 680, 740)

# ---- external systems of the same country (outside BionicPRO)
ext_idp = add_external(root1, "Удостоверяющие службы страны", "ЕСИА (РФ), eIDAS / BankID (ЕС) и др.",
    "Внешние IdP: вход через государственные и банковские службы страны по OIDC или SAML 2.0",
    980, 1060)
directory = add_external(root1, "Каталог учётных записей страны", "LDAP / Active Directory",
    "Внешний источник учётных данных в стране представительства. Персональные и медицинские данные "
    "не копируются за пределы страны", 1305, 1060)

# ---- web application (personal account) next to the mobile app
web = add_container(root1, "Веб-приложение (личный кабинет)", "React, TypeScript (SPA)",
    "Отчёты о работе протеза. Не получает и не хранит токены IdP — работает через BFF по cookie сессии",
    340, 160)

# ---- placeholder for the next country
other = add_boundary(root1, "Контур страны присутствия: страна N",
                     "Deployment Node: тот же состав, что и в контуре РФ", 20, 1060, 560, 150)
add_text(root1,
    "BFF / Auth Gateway · Keycloak страны · БД Keycloak · Redis<br>"
    "→ федерация с каталогом учётных записей страны N<br>"
    "→ брокеры к удостоверяющим службам страны N<br>"
    "Учётные, персональные и медицинские данные не покидают страну",
    40, 1070, 520, 90)

# ---- relationships
add_rel(root1, ID["pilot"], web, "Просмотр и скачивание отчётов", "HTTPS, браузер",
        exit=(0.5, 0), entry=(0, 0.5))
add_rel(root1, web, bff, "Вход и вызовы API", "HTTPS, cookie сессии",
        exit=(1, 0.5), entry=(0.25, 0), points=[(740, 220)], lx=0.3)
add_rel(root1, ID["mobile"], bff, "Вход и вызовы API", "HTTPS, cookie сессии",
        exit=(1, 0.1), entry=(0, 0.85), ly=-16)
add_rel(root1, bff, kc, "Authorization Code + PKCE,\nобмен code на токены, refresh, logout",
        "OIDC, back-channel HTTPS, client_secret", exit=(1, 0.5), entry=(0, 0.5))
add_rel(root1, bff, sessions, "Токены IdP по session id", "TCP, TLS", exit=(0.5, 1), entry=(0.5, 0))
add_rel(root1, bff, ID["api"], "Проксирование запросов пользователя", "HTTPS, Authorization: Bearer JWT",
        exit=(0.75, 0), entry=(0.25, 1), points=[(860, 450), (1560, 450)], lx=-0.6)
add_rel(root1, ID["api"], kc, "Проверка подписи и claims JWT", "JWKS (кэш), OIDC discovery",
        exit=(0, 0.6), entry=(0.85, 0), ly=-22)
add_rel(root1, kc, kc_db, "Чтение и запись", "JDBC", exit=(0.5, 1), entry=(0.5, 0))
add_rel(root1, kc, directory, "User Federation:\nпроверка учётных данных\nи атрибутов без импорта",
        "LDAPS", exit=(1, 0.75), entry=(0.5, 0), points=[(1425, 632)], lx=0.55)
add_rel(root1, kc, ext_idp, "Identity Brokering:\nвход через удостоверяющие\nслужбы страны", "OIDC / SAML 2.0",
        exit=(0, 0.75), entry=(0.5, 0), points=[(1100, 632)], lx=0.55)
add_rel(root1, ID["shop"], kc, "SSO покупателей и сотрудников", "OIDC", exit=(0.75, 1), entry=(0.25, 0), lx=0.3)
add_rel(root1, ID["crm"], kc, "SSO сотрудников", "OIDC", exit=(0.25, 1), entry=(0.5, 0), lx=0.3)

# ---- legend
add_note(root1,
    "<b>Обозначения</b><br>"
    "<font color='#B85450'>——&gt;</font> связи, добавленные в to-be<br>"
    "——&gt; связи из as-is<br>"
    "серый блок — внешняя система страны присутствия<br><br>"
    "<b>Ключевые решения</b><br>"
    "1. Один контур доступа на страну: Keycloak, его БД, BFF и Redis развёрнуты в стране; "
    "учётные данные берутся из местного каталога (федерация без импорта).<br>"
    "2. Токены IdP никогда не покидают серверную часть: клиент получает только opaque session id "
    "в HttpOnly-cookie (паттерн BFF).<br>"
    "3. Новые страны и внешние IdP подключаются через Identity Brokering Keycloak, без изменения приложений.",
    1520, 740, 230, 270)

# ================================================================ PAGE 2: token flow (sequence diagram)
page2 = ET.SubElement(mxfile, "diagram", name="Поток токенов (BFF)", id="task1-token-flow")
model2 = ET.SubElement(page2, "mxGraphModel", dx="1400", dy="900", grid="1", gridSize="10", guides="1",
                       tooltips="1", connect="1", arrows="1", fold="1", page="1", pageScale="1",
                       pageWidth="1654", pageHeight="1169", math="0", shadow="0")
root2 = ET.SubElement(model2, "root")
ET.SubElement(root2, "mxCell", id="0")
ET.SubElement(root2, "mxCell", id="1", parent="0")

LIFE_H = 1260
LIFE_W = 190
LIFE_STYLE = ("shape=umlLifeline;perimeter=lifelinePerimeter;whiteSpace=wrap;html=1;container=1;"
              "dropTarget=0;collapsible=0;recursiveResize=0;outlineConnect=0;portConstraint=eastwest;"
              "size=60;fontSize=12;fontStyle=1;fillColor=%s;strokeColor=%s;fontColor=#ffffff;")
MSG_STYLE = ("html=1;verticalAlign=bottom;endArrow=block;endFill=1;curved=0;rounded=0;fontSize=10;"
             "align=center;spacingBottom=2;")
RET_STYLE = MSG_STYLE + "dashed=1;dashPattern=6 4;endArrow=open;endFill=0;"


def add_lifeline(name, x, colour=("#23A2D9", "#0E7DAD")):
    c = ET.SubElement(root2, "mxCell", id=new_id("seq"), value=name, vertex="1", parent="1",
                      style=LIFE_STYLE % colour)
    g = ET.SubElement(c, "mxGeometry", x=str(x), y="80", width=str(LIFE_W), height=str(LIFE_H))
    g.set("as", "geometry")
    return c.get("id"), x + LIFE_W / 2


def add_msg(src, dst, y, text, ret=False):
    f = (y - 80) / LIFE_H
    anchor = f"exitX=0.5;exitY={f:.4f};exitDx=0;exitDy=0;entryX=0.5;entryY={f:.4f};entryDx=0;entryDy=0;"
    c = ET.SubElement(root2, "mxCell", id=new_id("seq"), value=text, edge="1", parent="1",
                      style=(RET_STYLE if ret else MSG_STYLE) + anchor, source=src[0], target=dst[0])
    g = ET.SubElement(c, "mxGeometry", relative="1")
    g.set("as", "geometry")
    sp = ET.SubElement(g, "mxPoint", x=str(src[1]), y=str(y)); sp.set("as", "sourcePoint")
    tp = ET.SubElement(g, "mxPoint", x=str(dst[1]), y=str(y)); tp.set("as", "targetPoint")


def add_section(y, text):
    c = ET.SubElement(root2, "mxCell", id=new_id("seq"), value=text, vertex="1", parent="1",
                      style="text;html=1;align=left;verticalAlign=middle;fontSize=12;fontStyle=1;"
                            "fillColor=#F5F5F5;strokeColor=#CCCCCC;spacingLeft=8;")
    g = ET.SubElement(c, "mxGeometry", x="20", y=str(y - 14), width="1700", height="28")
    g.set("as", "geometry")


def add_seq_note(x, y, w, h, text):
    c = ET.SubElement(root2, "mxCell", id=new_id("seq"), value=text, vertex="1", parent="1",
                      style="shape=note;size=12;whiteSpace=wrap;html=1;fillColor=#fff2cc;strokeColor=#d6b656;"
                            "align=left;verticalAlign=top;spacing=6;fontSize=10;fontColor=#333333;")
    g = ET.SubElement(c, "mxGeometry", x=str(x), y=str(y), width=str(w), height=str(h))
    g.set("as", "geometry")


# Sections are drawn first so they stay behind the lifelines.
add_section(200, "A. Вход пользователя (Authorization Code + PKCE выполняет BFF, а не браузер)")
add_section(720, "B. Вызов API: браузер предъявляет только cookie сессии")
add_section(1080, "C. Выход")

browser = add_lifeline("Браузер / мобильное<br>приложение", 40, ("#6C6477", "#4D4D4D"))
bff_l = add_lifeline("BFF / Auth Gateway", 320)
redis_l = add_lifeline("Хранилище сессий<br>(Redis)", 600)
kc_l = add_lifeline("Keycloak<br>(IdP страны)", 880)
idp_l = add_lifeline("Каталог УЗ страны /<br>внешний IdP", 1160, ("#8C8496", "#736782"))
api_l = add_lifeline("API", 1440)

# --- A. login
add_msg(browser, bff_l, 240, "1. GET /login")
add_seq_note(560, 250, 300, 44,
             "BFF создаёт state, nonce, code_verifier;<br>code_challenge = BASE64URL(SHA-256(code_verifier)); "
             "хранит их на сервере под временным cookie")
add_msg(bff_l, browser, 320, "2. 302 → Keycloak /authorize?response_type=code&amp;client_id=bff"
                              "<br>&amp;code_challenge=…&amp;code_challenge_method=S256&amp;state&amp;nonce", ret=True)
add_msg(browser, kc_l, 370, "3. GET /authorize — форма входа Keycloak")
add_msg(kc_l, idp_l, 410, "4. LDAP bind (проверка пароля без импорта пользователя)<br>или редирект на внешний IdP (OIDC / SAML brokering)")
add_msg(idp_l, kc_l, 450, "5. результат аутентификации / assertion", ret=True)
add_msg(kc_l, browser, 490, "6. 302 → BFF /callback?code=…&amp;state=…", ret=True)
add_msg(browser, bff_l, 530, "7. GET /callback?code&amp;state")
add_msg(bff_l, kc_l, 570, "8. POST /token: grant_type=authorization_code, code, code_verifier,<br>client_id + client_secret (back-channel)")
add_msg(kc_l, bff_l, 600, "9. access_token (JWT, ~5 мин), refresh_token, id_token", ret=True)
add_msg(bff_l, redis_l, 640, "10. SET sid → {access, refresh, id, exp}")
add_msg(bff_l, browser, 680, "11. 302 / + Set-Cookie: sid=&lt;256-bit random&gt;;<br>HttpOnly; Secure; SameSite=Strict", ret=True)

# --- B. API call
add_msg(browser, bff_l, 750, "12. GET /api/reports (Cookie: sid, X-CSRF-Token)")
add_msg(bff_l, redis_l, 790, "13. GET sid → токены")
add_seq_note(330, 805, 300, 30, "access истёк? → шаги 14–15, иначе сразу 16")
add_msg(bff_l, kc_l, 860, "14. POST /token: grant_type=refresh_token")
add_msg(kc_l, bff_l, 890, "15. новая пара access / refresh (ротация, старый refresh отозван)", ret=True)
add_msg(bff_l, api_l, 940, "16. GET /reports — Authorization: Bearer &lt;access JWT&gt;")
add_msg(api_l, kc_l, 975, "17. GET /certs (JWKS, кэшируется) — проверка подписи, iss, aud, exp,<br>роль prothetic_user; данные фильтруются по sub")
add_msg(api_l, bff_l, 1015, "18. 200 отчёт", ret=True)
add_msg(bff_l, browser, 1040, "19. 200 отчёт", ret=True)

# --- C. logout
add_msg(browser, bff_l, 1120, "20. POST /logout")
add_msg(bff_l, kc_l, 1160, "21. POST /logout (refresh_token) — отзыв сессии в Keycloak")
add_msg(bff_l, redis_l, 1200, "22. DEL sid")
add_msg(bff_l, browser, 1240, "23. 302 / + Set-Cookie: sid=; Max-Age=0", ret=True)

add_seq_note(1330, 20, 390, 50,
             "<b>Инвариант:</b> access-, refresh- и id-токены существуют только между BFF, Redis, "
             "Keycloak и API. Браузер и мобильное приложение видят только случайный session id.")

tree.write(OUT, encoding="utf-8", xml_declaration=False)
print("written", OUT)
