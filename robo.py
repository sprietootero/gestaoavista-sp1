"""
Robô de extração de dados do w1nner para Gestão à Vista - W1 SP1
"""

import os
import time
import json
import re
import csv
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


def extrair_ranking_muapd(page):
    print("  → Navegando para rankings...")
    page.goto(URL_RANKING, wait_until="networkidle")
    time.sleep(3)
    screenshot(page, "3_ranking_inicial")

    # Clica na aba "Tel Party" (ranking de AA/MUAPD)
    clicou_tab = False
    for seletor in [
        "text=Tel Party",
        "a:has-text('Tel Party')",
        "button:has-text('Tel Party')",
        "[href*='tel']",
    ]:
        try:
            page.locator(seletor).first.click()
            print(f"  ✓ Clicou na aba Tel Party via: {seletor}")
            clicou_tab = True
            time.sleep(3)
            break
        except Exception:
            pass

    if not clicou_tab:
        print("  ⚠ Não encontrou aba Tel Party — tentando sem clicar")

    screenshot(page, "4_ranking_tel_party")

    # IDs exatos extraídos do HTML do formulário Tel Party
    ID_DATA_COMPROMISSO = "tel_party_ranking_form_attribute_of_interest_calendar_event_start_at"
    # Critérios: manter apenas AA, desmarcar CA, SA, EA, AF, CF, SF, EF
    CRITERIOS_DESMARCAR = ["ca", "sa", "ea", "af", "cf", "sf", "ef"]
    ID_AA               = "tel_party_ranking_form_criterias_aa"

    # Passo 1: desativar "data de compromisso" (usar ID exato do campo)
    print("  → Desativando 'data de compromisso'...")
    try:
        cb = page.locator(f"#{ID_DATA_COMPROMISSO}")
        if cb.is_checked():
            cb.click()
            print("  ✓ 'data de compromisso' desmarcado")
        else:
            print("  ✓ 'data de compromisso' já desmarcado")
        time.sleep(0.5)
    except Exception as e:
        print(f"  ⚠ 'data de compromisso': {e}")

    screenshot(page, "4b_data_compromisso")

    # Passo 2: desmarcar critérios, manter apenas AA
    # (Não filtramos por escritório no formulário — filtramos em Python pela coluna 'escritório')
    print("  → Ajustando critérios (apenas AA)...")
    for valor in CRITERIOS_DESMARCAR:
        id_cb = f"tel_party_ranking_form_criterias_{valor}"
        try:
            cb = page.locator(f"#{id_cb}")
            if cb.is_checked():
                cb.click()
                print(f"  ✓ Critério '{valor.upper()}' desmarcado")
            time.sleep(0.3)
        except Exception as e:
            print(f"  ⚠ Critério '{valor}': {e}")

    try:
        cb_aa = page.locator(f"#{ID_AA}")
        if not cb_aa.is_checked():
            cb_aa.click()
            print("  ✓ 'AA' marcado")
        else:
            print("  ✓ 'AA' já marcado")
        time.sleep(0.3)
    except Exception as e:
        print(f"  ⚠ Critério AA: {e}")

    screenshot(page, "4c_criterios_ajustados")

    # Passo 3: aplicar filtro e aguardar resposta AJAX
    print("  → Aplicando filtro e aguardando AJAX...")
    try:
        with page.expect_response(
            lambda r: "ranking-tp" in r.url and r.status == 200,
            timeout=120_000
        ) as resp_info:
            page.get_by_role("button", name="Filtrar", exact=False).first.click()
            print("  ✓ Filtrar clicado — aguardando resposta do servidor...")
        print(f"  ✓ Resposta recebida: {resp_info.value.url[:80]}")
        time.sleep(3)  # deixa o DOM atualizar
    except Exception as e:
        print(f"  ⚠ expect_response falhou ({e}) — aguardando 30s como fallback")
        time.sleep(30)

    screenshot(page, "5_ranking_filtrado")

    html = page.content()
    (DEBUG_DIR / "ranking.html").write_text(html, encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")

    ranking = []

    todas_tabelas = soup.find_all("table")
    print(f"  → {len(todas_tabelas)} tabelas encontradas na página de ranking")

    tabela_ranking = None
    for t in todas_tabelas:
        headers = [th.get_text(strip=True).lower() for th in t.find_all("th")]
        if any(h in headers for h in ["consultor", "nome", "assessor"]):
            tabela_ranking = t
            print(f"  ✓ Tabela de ranking identificada: colunas = {headers}")
            break

    if tabela_ranking:
        headers_raw = [th.get_text(strip=True) for th in tabela_ranking.find_all("th")]
        tbody = tabela_ranking.find("tbody")
        if tbody:
            posicao = 1
            for tr in tbody.find_all("tr"):
                cells = [td.get_text(strip=True) for td in tr.find_all("td")]
                if cells and any(c.strip() for c in cells):
                    row_raw = dict(zip(headers_raw, cells))
                    # Filtra apenas consultores do escritório SP1
                    escritorio = (row_raw.get("Escritório") or row_raw.get("escritório") or "")
                    if NOME_ESCRITORIO.lower() not in escritorio.lower():
                        continue
                    consultor = (row_raw.get("Consultor") or row_raw.get("consultor") or
                                 row_raw.get("Nome") or "")
                    aa_val    = (row_raw.get("AA") or row_raw.get("aa") or "0")
                    ranking.append({
                        "Posição":   posicao,
                        "Consultor": consultor,
                        "AA":        aa_val,
                    })
                    posicao += 1
    else:
        print("  ⚠ Tabela de ranking não identificada")

    print(f"  → {len(ranking)} entradas no ranking de SP1")
    if ranking:
        print(f"  → Primeiros: {[r['Consultor'] for r in ranking[:5]]}")

    return ranking


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
        browser = pw.chromium.launch(headless=False)  # False = visível para debug
        page = browser.new_page()
        page.set_viewport_size({"width": 1400, "height": 900})

        fazer_login(page, conta["email"], conta["senha"])
        dados_brutos, metas = extrair_tabela_economia(page)
        ranking = extrair_ranking_muapd(page)

        browser.close()

    linhas = []
    for raw in dados_brutos:
        consultor = raw.get("Consultor/Nível", raw.get("Consultor", ""))
        nome_lider = next((l for l in LIDERES if any(p.lower() in consultor.lower() for p in l.split())), consultor)
        linhas.append(montar_linha_lider(raw, nome_lider))

    campos_dados   = ["Equipe", "AA", "AF", "AP", "AP Valor", "REC", "PP Total"]
    campos_ranking = list(ranking[0].keys()) if ranking else ["Posição", "Consultor", "AA"]

    salvar_csv(linhas,   "dados_extraidos.csv", campos_dados)
    salvar_csv(ranking,  "ranking_muapd.csv",   campos_ranking)
    salvar_metas(metas)

    print()
    print(f"Screenshots de debug salvos em: {DEBUG_DIR.resolve()}")
    print("Extração concluída!")


if __name__ == "__main__":
    main()
