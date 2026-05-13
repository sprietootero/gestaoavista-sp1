"""
Robô de extração de dados do w1nner para Gestão à Vista - W1 SP1
Executa login, filtra pelo escritório SP1, extrai métricas e ranking MUAPD.
"""

import os
import time
import json
import re
import csv
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

load_dotenv()

URL_LOGIN   = "https://w1nner.w1consultoria.com.br/painel-consultor/entrar"
URL_DADOS   = "https://w1nner.w1consultoria.com.br/painel-consultor/centro-de-economia"
URL_RANKING = "https://w1nner.w1consultoria.com.br/painel-consultor/indicadores/rankings"

# Nome do escritório exatamente como aparece no filtro do w1nner
NOME_ESCRITORIO = os.getenv("NOME_ESCRITORIO", "W1 SP1")

# Líderes de equipe — ajuste se os nomes no w1nner forem diferentes
LIDERES = [
    "Eduardo Mello",
    "Gianlucca Venturi",
    "Renato Segri",
    "Filipe Guarnieri",
    "Rodolfo Contini",
    "Fernando Bianchi",
]

CONTAS = [
    {"email": os.getenv("CONTA1_EMAIL"), "senha": os.getenv("CONTA1_SENHA")},
]
if os.getenv("CONTA2_EMAIL"):
    CONTAS.append({"email": os.getenv("CONTA2_EMAIL"), "senha": os.getenv("CONTA2_SENHA")})


def fazer_login(page, email, senha):
    print(f"  → Fazendo login com {email}...")
    page.goto(URL_LOGIN, wait_until="networkidle")
    page.fill("id=consultant_person_email", email)
    page.fill("id=consultant_person_password", senha)
    page.click("input[name='commit']")
    page.wait_for_load_state("networkidle")
    if "entrar" in page.url:
        raise RuntimeError(f"Login falhou para {email}")
    print("  ✓ Login OK")


def aplicar_filtro_escritorio(page):
    print(f"  → Aplicando filtro: {NOME_ESCRITORIO}...")
    try:
        page.get_by_text(NOME_ESCRITORIO, exact=False).first.click()
        time.sleep(15)
        print("  ✓ Filtro aplicado")
    except Exception as e:
        print(f"  ⚠ Não encontrou filtro '{NOME_ESCRITORIO}': {e}")
        print("    Verifique o valor de NOME_ESCRITORIO no .env")


def extrair_tabela_economia(page):
    print("  → Extraindo tabela de economia...")
    page.goto(URL_DADOS, wait_until="networkidle")
    aplicar_filtro_escritorio(page)

    html = page.content()
    soup = BeautifulSoup(html, "html.parser")
    tabela = soup.find("table", {"id": "js-economy-center-table"})
    if not tabela:
        # tenta encontrar qualquer tabela
        tabela = soup.find("table")
    if not tabela:
        print("  ⚠ Tabela não encontrada")
        return [], {}

    headers = [th.get_text(strip=True) for th in tabela.find_all("th")]
    rows = []
    for tr in tabela.find("tbody").find_all("tr"):
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if cells:
            rows.append(dict(zip(headers, cells)))

    # Filtra apenas os líderes SP1
    dados_lideres = []
    for row in rows:
        consultor = row.get("Consultor/Nível", row.get("Consultor", ""))
        if any(lider.lower() in consultor.lower() for lider in LIDERES):
            dados_lideres.append(row)

    # Extrai metas (linha de cabeçalho ou seção dedicada)
    metas = extrair_metas_da_pagina(soup)

    print(f"  ✓ {len(dados_lideres)} líderes encontrados")
    return dados_lideres, metas


def extrair_metas_da_pagina(soup):
    """Tenta extrair metas do painel. Retorna dict com o que encontrar."""
    metas = {}
    # Procura padrões comuns de exibição de meta
    textos = soup.get_text(" ", strip=True)

    # Padrões: "Meta AP Mês R$ 200.000" ou similar
    padrao_rs = re.compile(r"(Meta\s+\w+(?:\s+\w+)?)\s+R\$\s*([\d.,]+)", re.IGNORECASE)
    for m in padrao_rs.finditer(textos):
        chave = m.group(1).strip().lower().replace(" ", "_")
        valor = m.group(2).strip()
        metas[chave] = valor

    # Padrões: "Meta PPs Mês 3.700" ou similar
    padrao_pp = re.compile(r"(Meta\s+PP[s]?\s+\w+)\s+([\d.,]+)\s*PP", re.IGNORECASE)
    for m in padrao_pp.finditer(textos):
        chave = m.group(1).strip().lower().replace(" ", "_")
        valor = m.group(2).strip()
        metas[chave] = valor

    return metas


def extrair_ranking_muapd(page):
    print("  → Extraindo ranking MUAPD...")
    page.goto(URL_RANKING, wait_until="networkidle")
    time.sleep(3)

    # Tenta clicar no tab/link do ranking de AA (Tel Party / MUAPD)
    for nome_tab in ["Tel Party", "MUAPD", "AA"]:
        try:
            page.get_by_role("link", name=nome_tab).first.click()
            time.sleep(2)
            break
        except Exception:
            pass

    # Filtra escritório
    try:
        page.get_by_text(NOME_ESCRITORIO, exact=False).first.click()
        time.sleep(3)
    except Exception:
        pass

    html = page.content()
    soup = BeautifulSoup(html, "html.parser")

    ranking = []
    tabela = soup.find("table")
    if tabela:
        headers = [th.get_text(strip=True) for th in tabela.find_all("th")]
        for i, tr in enumerate(tabela.find("tbody").find_all("tr")):
            cells = [td.get_text(strip=True) for td in tr.find_all("td")]
            if cells:
                row = dict(zip(headers, cells))
                row["Posição"] = i + 1
                ranking.append(row)
    else:
        # fallback: lista de itens
        itens = soup.select("[class*='ranking'] li, [class*='rank'] li")
        for i, item in enumerate(itens):
            ranking.append({"Posição": i + 1, "Consultor": item.get_text(strip=True), "AA": ""})

    print(f"  ✓ {len(ranking)} consultores no ranking")
    return ranking


def montar_linha_lider(raw, nome_exibicao):
    """Mapeia colunas do w1nner para o formato do dashboard."""
    def val(keys):
        for k in keys:
            v = raw.get(k, "")
            if v:
                return v
        return "0"

    return {
        "Equipe": nome_exibicao,
        "AA":     val(["AA", "Meta AA"]),
        "AF":     val(["AF"]),
        "AP":     val(["AP"]),
        "AP Valor": val(["AP [R$]", "AP Valor", "AP[R$]"]),
        "REC":    val(["Recs", "REC", "Rec"]),
        "PP Total": val(["Total", "PP Total", "PPs"]),
    }


def salvar_csv(dados, caminho, fieldnames):
    with open(caminho, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(dados)
    print(f"  ✓ Salvo: {caminho}")


def salvar_metas(metas_brutas, caminho="metas.json"):
    # Tenta mapear para os campos conhecidos do dashboard
    mapeamento = {
        "meta_ap_semana": "",
        "meta_pp_semana": "",
        "meta_ap_mes":    "",
        "meta_pp_mes":    "",
    }
    for k, v in metas_brutas.items():
        kl = k.lower()
        if "ap" in kl and "semana" in kl:
            mapeamento["meta_ap_semana"] = v
        elif "pp" in kl and "semana" in kl:
            mapeamento["meta_pp_semana"] = v
        elif "ap" in kl and "m" in kl:
            mapeamento["meta_ap_mes"] = v
        elif "pp" in kl and "m" in kl:
            mapeamento["meta_pp_mes"] = v

    # Se não extraiu nada, mantém valores do arquivo existente
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

        fazer_login(page, conta["email"], conta["senha"])
        dados_brutos, metas = extrair_tabela_economia(page)
        ranking = extrair_ranking_muapd(page)

        browser.close()

    # Monta dados dos líderes no formato do dashboard
    linhas = []
    for raw in dados_brutos:
        consultor = raw.get("Consultor/Nível", raw.get("Consultor", ""))
        nome_lider = next(
            (l for l in LIDERES if l.lower() in consultor.lower()), consultor
        )
        linhas.append(montar_linha_lider(raw, nome_lider))

    campos_dados = ["Equipe", "AA", "AF", "AP", "AP Valor", "REC", "PP Total"]
    campos_ranking = list(ranking[0].keys()) if ranking else ["Posição", "Consultor", "AA"]

    salvar_csv(linhas, "dados_extraidos.csv", campos_dados)
    salvar_csv(ranking, "ranking_muapd.csv", campos_ranking)
    salvar_metas(metas)

    print()
    print("Extração concluída! Faça git add + commit + push para atualizar o dashboard.")


if __name__ == "__main__":
    main()
