"""
Robô de extração de dados do w1nner para Gestão à Vista - W1 SP1
"""

import os
import time
import json
import re
import csv
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

load_dotenv()

URL_LOGIN   = "https://w1nner.w1consultoria.com.br/painel-consultor/entrar"
URL_DADOS   = "https://w1nner.w1consultoria.com.br/painel-consultor/centro-de-economia"
URL_RANKING = "https://w1nner.w1consultoria.com.br/painel-consultor/indicadores/rankings"

NOME_ESCRITORIO = os.getenv("NOME_ESCRITORIO", "W1 SP 1")

LIDERES = [
    "Eduardo Mello",
    "Gianlucca Venturi",
    "Renato Segri",
    "Filipe Guarnieri",
    "Rodolfo Contini",
    "Fernando Bianchi",
]

CONTAS = [{"email": os.getenv("CONTA1_EMAIL"), "senha": os.getenv("CONTA1_SENHA")}]
if os.getenv("CONTA2_EMAIL"):
    CONTAS.append({"email": os.getenv("CONTA2_EMAIL"), "senha": os.getenv("CONTA2_SENHA")})

DEBUG_DIR = Path("debug")
DEBUG_DIR.mkdir(exist_ok=True)


def screenshot(page, nome):
    try:
        path = str(DEBUG_DIR / f"{nome}.png")
        page.screenshot(path=path, timeout=10000)
        print(f"  📸 Screenshot: {path}")
    except Exception:
        pass  # screenshot é só debug, não bloqueia


def fazer_login(page, email, senha):
    print(f"  → Fazendo login com {email}...")
    page.goto(URL_LOGIN, wait_until="networkidle")
    page.fill("id=consultant_person_email", email)
    page.fill("id=consultant_person_password", senha)
    page.click("input[name='commit']")
    page.wait_for_load_state("networkidle")
    if "entrar" in page.url:
        screenshot(page, "erro_login")
        raise RuntimeError(f"Login falhou para {email}")
    print("  ✓ Login OK")


def extrair_tabela_economia(page):
    print("  → Navegando para centro de economia...")
    page.goto(URL_DADOS, wait_until="networkidle")
    time.sleep(3)
    screenshot(page, "1_economia_inicial")

    # Passo 1: clicar em "Selecionar todos os escritórios" para desmarcar tudo
    print("  → Desmarcando todos via 'Selecionar todos os escritórios'...")
    page.get_by_text("Selecionar todos os escritórios", exact=False).first.click()
    time.sleep(1)
    screenshot(page, "2a_todos_desmarcados")

    # Passo 2: marcar apenas W1 SP 1
    print(f"  → Marcando apenas: {NOME_ESCRITORIO}...")
    page.get_by_text(NOME_ESCRITORIO, exact=True).first.click()
    print("  ✓ Escritório selecionado")
    time.sleep(1)
    screenshot(page, "2b_sp1_selecionado")

    # Passo 3: clicar em "Filtrar"
    page.get_by_role("button", name="Filtrar", exact=False).first.click()
    print("  ✓ Filtro aplicado")

    print("  → Aguardando tabela carregar (20s)...")
    time.sleep(20)
    screenshot(page, "2_economia_filtrada")

    html = page.content()
    # Salva HTML para análise
    (DEBUG_DIR / "economia.html").write_text(html, encoding="utf-8")

    soup = BeautifulSoup(html, "html.parser")

    # Tenta encontrar a tabela pelo ID conhecido, depois por qualquer tabela grande
    tabela = soup.find("table", {"id": "js-economy-center-table"})
    if not tabela:
        todas = soup.find_all("table")
        # Pega a tabela com mais linhas (mais provável ser a de dados)
        tabela = max(todas, key=lambda t: len(t.find_all("tr")), default=None) if todas else None
        if tabela:
            print(f"  ⚠ Tabela principal não encontrada por ID, usando maior tabela ({len(tabela.find_all('tr'))} linhas)")

    if not tabela:
        print("  ✗ Nenhuma tabela encontrada na página")
        return [], {}

    # A tabela tem 2 linhas de cabeçalho — usa apenas a última (nomes reais das colunas)
    thead = tabela.find("thead")
    header_rows = thead.find_all("tr") if thead else []
    last_row = header_rows[-1] if header_rows else tabela.find("tr")
    headers = [th.get_text(strip=True) for th in last_row.find_all("th")]
    headers[0] = "Consultor/Nível"  # primeira célula vem da linha de grupo acima
    print(f"  → Colunas encontradas: {headers[:12]}")

    tbody = tabela.find("tbody")
    if not tbody:
        print("  ✗ Tabela sem tbody")
        return [], {}

    rows = []
    for tr in tbody.find_all("tr"):
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if cells:
            rows.append(dict(zip(headers, cells)))

    print(f"  → Total de linhas na tabela: {len(rows)}")

    # Mostra os primeiros nomes encontrados para debug
    nomes_encontrados = [r.get("Consultor/Nível", r.get("Consultor", "?")) for r in rows[:10]]
    print(f"  → Primeiros nomes: {nomes_encontrados}")

    # Filtra líderes
    dados_lideres = []
    for row in rows:
        consultor = row.get("Consultor/Nível", row.get("Consultor", ""))
        # Busca por qualquer palavra do nome do líder
        for lider in LIDERES:
            partes = lider.lower().split()
            if any(p in consultor.lower() for p in partes):
                dados_lideres.append(row)
                print(f"  ✓ Líder encontrado: {consultor}")
                break

    metas = extrair_metas_da_pagina(soup)
    print(f"  → {len(dados_lideres)} líderes encontrados de {len(LIDERES)} esperados")
    return dados_lideres, metas


def extrair_metas_da_pagina(soup):
    metas = {}
    textos = soup.get_text(" ", strip=True)
    padrao_rs = re.compile(r"(Meta\s+\w+(?:\s+\w+)?)\s+R\$\s*([\d.,]+)", re.IGNORECASE)
    for m in padrao_rs.finditer(textos):
        chave = m.group(1).strip().lower().replace(" ", "_")
        metas[chave] = m.group(2).strip()
    padrao_pp = re.compile(r"(Meta\s+PP[s]?\s+\w+)\s+([\d.,]+)\s*PP", re.IGNORECASE)
    for m in padrao_pp.finditer(textos):
        chave = m.group(1).strip().lower().replace(" ", "_")
        metas[chave] = m.group(2).strip()
    return metas


def _aplicar_filtros_tel_party(page, data_inicio_str, data_fim_str, sufixo_screenshot):
    """Aplica filtros de critério e data no formulário Tel Party e aguarda AJAX."""
    ID_DATA_COMPROMISSO = "tel_party_ranking_form_attribute_of_interest_calendar_event_start_at"
    ID_DATA_INICIO      = "tel_party_ranking_form_created_at_start_period_date"
    ID_DATA_FIM         = "tel_party_ranking_form_created_at_end_period_date"
    CRITERIOS_DESMARCAR = ["ca", "sa", "ea", "af", "cf", "sf", "ef"]
    ID_AA               = "tel_party_ranking_form_criterias_aa"

    # Desativar "data de compromisso"
    try:
        cb = page.locator(f"#{ID_DATA_COMPROMISSO}")
        if cb.is_checked():
            cb.click()
        time.sleep(0.3)
    except Exception as e:
        print(f"  ⚠ data de compromisso: {e}")

    # Ajustar intervalo de datas via triple-click + type (datepicker Bootstrap)
    def preencher_data(campo_id, valor):
        try:
            inp = page.locator(f"#{campo_id}")
            inp.click(click_count=3)  # seleciona tudo
            page.keyboard.type(valor)
            page.keyboard.press("Tab")
            time.sleep(0.3)
        except Exception as e:
            print(f"  ⚠ Data {campo_id}: {e}")

    preencher_data(ID_DATA_INICIO, data_inicio_str)
    preencher_data(ID_DATA_FIM,    data_fim_str)
    print(f"  ✓ Datas: {data_inicio_str} → {data_fim_str}")

    # Desmarcar critérios, manter apenas AA
    for valor in CRITERIOS_DESMARCAR:
        try:
            cb = page.locator(f"#tel_party_ranking_form_criterias_{valor}")
            if cb.is_checked():
                cb.click()
            time.sleep(0.2)
        except Exception:
            pass
    try:
        cb_aa = page.locator(f"#{ID_AA}")
        if not cb_aa.is_checked():
            cb_aa.click()
        time.sleep(0.2)
    except Exception as e:
        print(f"  ⚠ Critério AA: {e}")

    screenshot(page, f"4_{sufixo_screenshot}_filtros")

    # Aplicar filtro e aguardar AJAX
    try:
        with page.expect_response(
            lambda r: "ranking-tp" in r.url and r.status == 200,
            timeout=20_000
        ):
            page.get_by_role("button", name="Filtrar", exact=False).first.click()
            print("  ✓ Filtrar clicado — aguardando AJAX...")
        time.sleep(3)
    except Exception as e:
        print(f"  ⚠ expect_response: {e} — aguardando 10s")
        time.sleep(10)

    screenshot(page, f"5_{sufixo_screenshot}_resultado")


def _parsear_ranking_da_pagina(page, sufixo_debug):
    """Extrai e retorna o ranking de SP1 do HTML atual da página."""
    html = page.content()
    (DEBUG_DIR / f"ranking_{sufixo_debug}.html").write_text(html, encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")

    HEADERS = ["#", "Consultor", "Cargo", "Escritório", "AA", "TOTAL", "MÉDIA", "BP"]
    ranking = []

    tabela_ranking = None
    for t in soup.find_all("table"):
        headers = [th.get_text(strip=True).lower() for th in t.find_all("th")]
        if any(h in headers for h in ["consultor", "nome", "assessor"]):
            tabela_ranking = t
            break

    if not tabela_ranking:
        print("  ⚠ Tabela de ranking não identificada")
        return ranking

    thead = tabela_ranking.find("thead")
    all_trs = thead.find_all("tr") if thead else tabela_ranking.find_all("tr")
    posicao = 1
    for tr in all_trs:
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(cells) < 4:
            continue
        row_raw = dict(zip(HEADERS, cells))
        if row_raw.get("#", "").lower() in ("total", ""):
            continue
        escritorio = row_raw.get("Escritório", "")
        if NOME_ESCRITORIO.lower() not in escritorio.lower():
            continue
        ranking.append({
            "Posição":   posicao,
            "Consultor": row_raw.get("Consultor", ""),
            "AA":        row_raw.get("AA", "0"),
        })
        posicao += 1

    print(f"  → {len(ranking)} entradas ({sufixo_debug})")
    if ranking:
        print(f"  → Top 3: {[r['Consultor'] for r in ranking[:3]]}")
    return ranking


def _parsear_top10_ap(html):
    """Extrai top 10 consultores por AP Valor do HTML da página de rankings."""
    soup = BeautifulSoup(html, "html.parser")
    ranking = []

    tabela = None
    for t in soup.find_all("table"):
        all_text = [c.get_text(strip=True).lower()
                    for c in t.find_all(["th", "td"])]
        if any(h in all_text for h in ["consultor", "nome", "assessor"]):
            tabela = t
            break

    if not tabela:
        print("  ⚠ Tabela AP não encontrada no HTML")
        return ranking

    # Cabeçalhos: última linha de <th> no thead
    headers = []
    thead = tabela.find("thead")
    if thead:
        for tr in thead.find_all("tr"):
            ths = [th.get_text(strip=True) for th in tr.find_all("th")]
            if ths:
                headers = ths  # sobrescreve até a última linha com th
    print(f"  → Colunas AP: {headers}")

    # Dados estão no <tbody> (diferente do Tel Party que usa thead)
    tbody = tabela.find("tbody")
    if not tbody:
        print("  ⚠ Tabela AP sem tbody")
        return ranking

    posicao = 1
    for tr in tbody.find_all("tr"):
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(cells) < 3:
            continue

        # Pular linha de Total/cabeçalho repetido
        if cells[0].strip().lower() in ("total", "#", ""):
            continue

        row_raw = dict(zip(headers, cells)) if headers else {}

        # Filtrar pelo escritório atual do consultor
        escritorio = row_raw.get("Escritório atual do consultor", "")
        if escritorio and NOME_ESCRITORIO.lower() not in escritorio.lower():
            continue

        # Consultor: coluna explícita ou índice 2 (padrão: #, ID, Consultor, ...)
        consultor = (row_raw.get("Consultor") or row_raw.get("Nome") or
                     row_raw.get("Assessor") or
                     (cells[2] if len(cells) > 2 else ""))
        if not consultor or consultor in ("-", "–") or consultor.lower() in ("consultor", "nome"):
            continue

        # AP Valor: coluna "Valor" ou índice 5 (posicional)
        ap_valor = row_raw.get("Valor", "")
        if not ap_valor and len(cells) > 5:
            ap_valor = cells[5]
        if not ap_valor:
            for c in cells:
                if "R$" in c:
                    ap_valor = c
                    break

        ranking.append({
            "Posição":   posicao,
            "Consultor": consultor,
            "AP Valor":  ap_valor,
        })
        posicao += 1

    top10 = ranking[:10]
    print(f"  → {len(ranking)} entradas totais, top 10: {[r['Consultor'] for r in top10]}")
    return top10


def extrair_top10_ap(page):
    """Extrai top 10 consultores por AP do mês via página de Rankings."""
    print("\n  [ Top 10 AP do Mês ]")
    page.goto(URL_RANKING, wait_until="networkidle")
    time.sleep(3)
    screenshot(page, "6_top10ap_inicial")

    # Selecionar aba "APs" no topo da página
    for seletor in ["text=APs", "a:has-text('APs')", "button:has-text('APs')", "[href*='ap']"]:
        try:
            page.locator(seletor).first.click()
            print(f"  ✓ Aba APs clicada: {seletor}")
            time.sleep(3)
            break
        except Exception as e:
            print(f"  ⚠ {seletor}: {e}")
    screenshot(page, "6b_top10ap_apos_aba")

    # Preencher "Escritório da produção" com W1 SP 1 (campo select2/autocomplete)
    try:
        campo = page.get_by_label("Escritório da produção", exact=False).first
        campo.click()
        time.sleep(0.5)
        campo.fill(NOME_ESCRITORIO)
        time.sleep(1)
        # Clica na primeira opção do dropdown que contém o nome
        page.get_by_text(NOME_ESCRITORIO, exact=True).first.click()
        print(f"  ✓ Escritório da produção: {NOME_ESCRITORIO}")
        time.sleep(0.5)
    except Exception as e:
        print(f"  ⚠ Escritório da produção: {e}")

    screenshot(page, "6c_top10ap_filtro")

    # Clicar Filtrar e aguardar resposta
    try:
        with page.expect_response(
            lambda r: r.status == 200 and ("ranking" in r.url or "indicador" in r.url),
            timeout=15_000
        ):
            page.get_by_role("button", name="Filtrar", exact=False).first.click()
            print("  ✓ Filtrar clicado — aguardando...")
        time.sleep(5)
    except Exception as e:
        print(f"  ⚠ expect_response: {e} — aguardando 10s")
        time.sleep(10)

    screenshot(page, "6d_top10ap_resultado")

    html = page.content()
    (DEBUG_DIR / "top10_ap.html").write_text(html, encoding="utf-8")
    return _parsear_top10_ap(html)


def extrair_rankings_muapd(page):
    """Extrai dois rankings: hoje e últimos 7 dias."""
    hoje      = datetime.now()
    sete_dias = hoje - timedelta(days=7)
    fmt       = lambda d: d.strftime("%d/%m/%Y")

    print("  → Navegando para rankings...")
    page.goto(URL_RANKING, wait_until="networkidle")
    time.sleep(3)
    screenshot(page, "3_ranking_inicial")

    # Clicar na aba Tel Party
    for seletor in ["text=Tel Party", "a:has-text('Tel Party')", "[href*='tel']"]:
        try:
            page.locator(seletor).first.click()
            print(f"  ✓ Aba Tel Party: {seletor}")
            time.sleep(3)
            break
        except Exception:
            pass

    # ── Ranking HOJE ──
    print("\n  [ Ranking HOJE ]")
    _aplicar_filtros_tel_party(page, fmt(hoje), fmt(hoje), "hoje")
    ranking_hoje = _parsear_ranking_da_pagina(page, "hoje")

    # ── Ranking 7 DIAS — renavelga para estado limpo ──
    print("\n  [ Ranking 7 DIAS ]")
    page.goto(URL_RANKING, wait_until="networkidle")
    time.sleep(2)
    for seletor in ["text=Tel Party", "a:has-text('Tel Party')", "[href*='tel']"]:
        try:
            page.locator(seletor).first.click()
            time.sleep(2)
            break
        except Exception:
            pass
    _aplicar_filtros_tel_party(page, fmt(sete_dias), fmt(hoje), "7dias")
    ranking_7dias = _parsear_ranking_da_pagina(page, "7dias")

    return ranking_hoje, ranking_7dias


def montar_linha_lider(raw, nome_exibicao):
    def val(keys):
        for k in keys:
            v = raw.get(k, "")
            if v and v != "0":
                return v
        return "0"

    return {
        "Equipe":    nome_exibicao,
        "AA":        val(["AA"]),
        "AF":        val(["AF"]),
        "AP":        val(["AP"]),
        "AP Valor":  val(["AP [R$]", "AP Valor", "AP[R$]", "AP R$"]),
        "Meta AP":   val(["Meta AP [R$]", "Meta AP[R$]", "Meta AP R$"]),
        "REC":       val(["Recs", "REC", "Rec"]),
        "PP Total":  val(["Total", "PP Total", "PPs", "PP"]),
    }


def salvar_csv(dados, caminho, fieldnames):
    with open(caminho, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(dados)
    print(f"  ✓ Salvo: {caminho}")


def salvar_metas(metas_brutas, caminho="metas.json"):
    mapeamento = {"meta_ap_semana": "", "meta_pp_semana": "", "meta_ap_mes": "", "meta_pp_mes": ""}
    for k, v in metas_brutas.items():
        kl = k.lower()
        if "ap" in kl and "semana" in kl:    mapeamento["meta_ap_semana"] = v
        elif "pp" in kl and "semana" in kl:  mapeamento["meta_pp_semana"] = v
        elif "ap" in kl:                      mapeamento["meta_ap_mes"] = v
        elif "pp" in kl:                      mapeamento["meta_pp_mes"] = v

    if os.path.exists(caminho):
        with open(caminho, encoding="utf-8") as f:
            existente = json.load(f)
        for k in mapeamento:
            if not mapeamento[k] and existente.get(k):
                mapeamento[k] = existente[k]

    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(mapeamento, f, ensure_ascii=False, indent=2)
    print(f"  ✓ Metas salvas: {caminho}")


def main():
    conta = CONTAS[0]
    if not conta["email"] or not conta["senha"]:
        raise RuntimeError("Configure CONTA1_EMAIL e CONTA1_SENHA no arquivo .env")

    print("=" * 50)
    print("Gestão à Vista SP1 — Extração de Dados")
    print("=" * 50)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_viewport_size({"width": 1400, "height": 900})

        fazer_login(page, conta["email"], conta["senha"])
        dados_brutos, metas = extrair_tabela_economia(page)
        ranking_hoje, ranking_7dias = extrair_rankings_muapd(page)
        top10_ap = extrair_top10_ap(page)

        browser.close()

    linhas = []
    for raw in dados_brutos:
        consultor = raw.get("Consultor/Nível", raw.get("Consultor", ""))
        nome_lider = next((l for l in LIDERES if any(p.lower() in consultor.lower() for p in l.split())), consultor)
        linhas.append(montar_linha_lider(raw, nome_lider))

    campos_dados   = ["Equipe", "AA", "AF", "AP", "AP Valor", "Meta AP", "REC", "PP Total"]
    campos_ranking = ["Posição", "Consultor", "AA"]
    campos_top10   = ["Posição", "Consultor", "AP Valor"]

    salvar_csv(linhas,         "dados_extraidos.csv",  campos_dados)
    salvar_csv(ranking_hoje,   "ranking_muapd.csv",    campos_ranking)
    salvar_csv(ranking_7dias,  "ranking_7dias.csv",    campos_ranking)
    salvar_csv(top10_ap,       "top10_ap.csv",         campos_top10)
    salvar_metas(metas)

    print()
    print(f"Screenshots de debug salvos em: {DEBUG_DIR.resolve()}")
    print("Extração concluída!")


if __name__ == "__main__":
    main()
