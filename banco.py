"""Única parte do Rende que guarda e lê dados (hoje em SQLite, no arquivo rende.db).

Para trocar por Supabase (ou outro banco), reescreva só este arquivo mantendo
os mesmos nomes de funções. Nenhum outro arquivo fala SQL.

Datas e "dia" usam o horário de Brasília.
"""
import json
import os
import sqlite3
from datetime import date, datetime, timedelta, timezone

FUSO_BRASILIA = timezone(timedelta(hours=-3))  # o Brasil não tem horário de verão desde 2019
MAX_HISTORICO = 30

_conexao: sqlite3.Connection | None = None

ESQUEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    telegram_id         TEXT PRIMARY KEY,
    nome                TEXT,
    adultos             INTEGER,
    criancas            INTEGER,       -- criança = meia porção
    refeicoes           TEXT,          -- JSON: ["cafe", "almoco", "jantar", "lanche", "marmita"]
    dias                TEXT,          -- JSON: ["seg", "ter", ...]
    vibe                TEXT,
    restricoes          TEXT,          -- JSON: ["lactose", "gluten", ...]
    restricoes_outras   TEXT,          -- texto livre ("outro")
    utensilios          TEXT,          -- JSON: ["fogao", "forno", ...]
    mercados            TEXT,          -- JSON: ["assai", ...] ou ["qualquer"]
    periodo             TEXT,          -- 'semana' ou 'mes'
    orcamento           REAL,
    cidade              TEXT,
    latitude            REAL,
    longitude           REAL,
    localizacao_em      TEXT,
    preferencias        TEXT,          -- texto livre: gostos, observações
    preferencias_pratos TEXT,          -- JSON: {"prato": nota 1-5, ...}
    despensa            TEXT,          -- JSON: {"arroz": {"quantidade": 2500, "unidade": "g"}, ...}
    cadastro_passo      TEXT,          -- passo atual do cadastro (NULL = cadastro concluído)
    avisos_ativos       INTEGER NOT NULL DEFAULT 1,
    aviso_dia_semana    INTEGER NOT NULL DEFAULT 5,   -- 0 = segunda ... 5 = sábado, 6 = domingo
    aviso_horario       TEXT NOT NULL DEFAULT '09:00',
    ultimo_aviso_dia    TEXT,
    ultimo_resumo_dia   TEXT,
    criado_em           TEXT,
    atualizado_em       TEXT
);
CREATE TABLE IF NOT EXISTS historico (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id TEXT NOT NULL,
    papel       TEXT NOT NULL,     -- 'usuario' ou 'assistente'
    texto       TEXT NOT NULL,
    criado_em   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS historico_usuario ON historico (telegram_id, id);
CREATE TABLE IF NOT EXISTS planos (       -- o plano atual é o mais recente; guarda os 3 últimos
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id TEXT NOT NULL,
    semana      TEXT NOT NULL,     -- semana do ano (AAAA-Wnn), para despensa e variedade
    conteudo    TEXT NOT NULL,     -- JSON: refeições, produtos, lista por embalagem, receitas...
    criado_em   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS planos_usuario ON planos (telegram_id, id);
CREATE TABLE IF NOT EXISTS promocoes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    mercado         TEXT NOT NULL,
    produto         TEXT NOT NULL,
    preco           REAL NOT NULL,
    validade        TEXT NOT NULL, -- AAAA-MM-DD (último dia da oferta)
    cidade          TEXT,
    origem          TEXT NOT NULL, -- 'admin' (/promo), 'usuario' (encarte mandado pela pessoa) ou 'site' (coletor)
    marca           TEXT,
    tamanho         TEXT,
    preco_anterior  REAL,
    condicao        TEXT,
    validade_inicio TEXT,
    lojas           TEXT,
    fonte_url       TEXT,
    criado_em       TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS precos (       -- preços vistos de verdade (sem dizer quem informou)
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    produto     TEXT NOT NULL,         -- nome normalizado do item ("arroz", "feijao carioca")
    nome        TEXT NOT NULL,         -- como apareceu na lista ("Feijão carioca")
    embalagem   TEXT,                  -- "pacote 5 kg"
    tamanho     REAL,
    unidade     TEXT,                  -- 'g', 'ml' ou 'un'
    preco       REAL NOT NULL,         -- preço de UMA embalagem
    mercado     TEXT,                  -- quando a pessoa compra num mercado só
    cidade      TEXT,
    origem      TEXT NOT NULL,         -- 'usuario' (Modo mercado), 'site', 'encarte' ou 'admin'
    criado_em   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS precos_produto ON precos (produto, criado_em);
CREATE TABLE IF NOT EXISTS uso_diario (
    telegram_id TEXT NOT NULL,
    dia         TEXT NOT NULL,
    mensagens   INTEGER NOT NULL,
    PRIMARY KEY (telegram_id, dia)
);
CREATE TABLE IF NOT EXISTS uso_ia (       -- sem texto de conversa e sem usuário
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    criado_em      TEXT NOT NULL,
    dia            TEXT NOT NULL,
    provedor       TEXT NOT NULL,         -- 'gemini' ou 'claude'
    nivel          TEXT NOT NULL DEFAULT '',  -- 'gemini', 'gemini-reserva', 'haiku', 'sonnet', 'opus'
    modelo         TEXT NOT NULL,
    tarefa         TEXT NOT NULL,
    motivo         TEXT NOT NULL,
    tokens_entrada INTEGER NOT NULL,      -- entrada sem cache
    tokens_saida   INTEGER NOT NULL,      -- inclui o "raciocínio"
    cache_leitura  INTEGER NOT NULL DEFAULT 0,
    cache_escrita  INTEGER NOT NULL DEFAULT 0,
    custo_usd      REAL NOT NULL,
    cobrada        INTEGER NOT NULL,      -- 1 se o modelo respondeu (a chamada conta no gasto e no limite)
    escalonou_por  TEXT                   -- se esta chamada foi uma subida de nível: por quê
);
"""
# Colunas acrescentadas depois da primeira versão (o banco antigo ganha as colunas sozinho)
_COLUNAS_NOVAS = {"uso_ia": {"nivel": "TEXT NOT NULL DEFAULT ''", "cache_leitura": "INTEGER NOT NULL DEFAULT 0",
                             "cache_escrita": "INTEGER NOT NULL DEFAULT 0", "escalonou_por": "TEXT"},
                  # o que o Rende espera da próxima mensagem (ex.: "preco:7:3" = preço do item 3 do plano 7)
                  "usuarios": {"aguardando": "TEXT"}}

CAMPOS_PERFIL = {
    "nome", "adultos", "criancas", "refeicoes", "dias", "vibe", "restricoes", "restricoes_outras",
    "utensilios", "mercados", "periodo", "orcamento", "cidade", "latitude", "longitude",
    "localizacao_em", "preferencias", "preferencias_pratos", "despensa", "cadastro_passo",
    "avisos_ativos", "aviso_dia_semana", "aviso_horario", "ultimo_aviso_dia", "ultimo_resumo_dia",
    "aguardando",
}
# Guardados como JSON no banco e devolvidos como listas/dicionários
CAMPOS_JSON = {"refeicoes": list, "dias": list, "restricoes": list, "utensilios": list,
               "mercados": list, "preferencias_pratos": dict, "despensa": dict}


# --- conexão -----------------------------------------------------------------
def conectar(caminho: str | None = None) -> sqlite3.Connection:
    """Abre (ou cria) o banco. Sem caminho, usa BANCO_ARQUIVO do .env ou 'rende.db'."""
    global _conexao
    if _conexao is not None:
        _conexao.close()
    caminho = caminho or os.getenv("BANCO_ARQUIVO") or "rende.db"
    _conexao = sqlite3.connect(caminho, check_same_thread=False)
    _conexao.row_factory = sqlite3.Row
    _conexao.execute("PRAGMA foreign_keys = ON")
    _conexao.executescript(ESQUEMA)
    for tabela, colunas in _COLUNAS_NOVAS.items():
        existentes = {linha["name"] for linha in _conexao.execute(f"PRAGMA table_info({tabela})")}
        for coluna, tipo in colunas.items():
            if coluna not in existentes:
                _conexao.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")
    _conexao.commit()
    return _conexao


def _db() -> sqlite3.Connection:
    return _conexao or conectar()


def agora() -> datetime:
    return datetime.now(FUSO_BRASILIA)


def hoje() -> str:
    return agora().date().isoformat()


def _agora_txt() -> str:
    return agora().isoformat(timespec="seconds")


# --- usuários e perfil -------------------------------------------------------
def usuario(telegram_id: str) -> dict | None:
    linha = _db().execute("SELECT * FROM usuarios WHERE telegram_id = ?", (telegram_id,)).fetchone()
    if not linha:
        return None
    perfil = dict(linha)
    for campo, tipo in CAMPOS_JSON.items():
        perfil[campo] = json.loads(perfil[campo]) if perfil[campo] else tipo()
    return perfil


def obter_ou_criar_usuario(telegram_id: str) -> dict:
    if usuario(telegram_id) is None:
        _db().execute("INSERT INTO usuarios (telegram_id, criado_em, atualizado_em) VALUES (?, ?, ?)",
                      (telegram_id, _agora_txt(), _agora_txt()))
        _db().commit()
    return usuario(telegram_id)


def atualizar_perfil(telegram_id: str, **campos) -> dict:
    campos = {k: v for k, v in campos.items() if k in CAMPOS_PERFIL}
    for campo in CAMPOS_JSON:
        if campo in campos and not isinstance(campos[campo], str):
            campos[campo] = json.dumps(campos[campo], ensure_ascii=False)
    obter_ou_criar_usuario(telegram_id)
    if campos:
        colunas = ", ".join(f"{k} = ?" for k in campos)
        _db().execute(f"UPDATE usuarios SET {colunas}, atualizado_em = ? WHERE telegram_id = ?",
                      (*campos.values(), _agora_txt(), telegram_id))
        _db().commit()
    return usuario(telegram_id)


def apagar_usuario(telegram_id: str) -> None:
    """LGPD: apaga tudo o que se refere à pessoa (perfil, conversa, planos, contagem de uso)."""
    for tabela in ("historico", "planos", "uso_diario", "usuarios"):
        _db().execute(f"DELETE FROM {tabela} WHERE telegram_id = ?", (telegram_id,))
    _db().commit()


# --- histórico (últimas 30 mensagens) ----------------------------------------
def historico(telegram_id: str) -> list[dict]:
    linhas = _db().execute(
        "SELECT papel, texto FROM historico WHERE telegram_id = ? ORDER BY id DESC LIMIT ?",
        (telegram_id, MAX_HISTORICO)).fetchall()
    return [{"papel": l["papel"], "texto": l["texto"]} for l in reversed(linhas)]


def adicionar_mensagem(telegram_id: str, papel: str, texto: str) -> None:
    _db().execute("INSERT INTO historico (telegram_id, papel, texto, criado_em) VALUES (?, ?, ?, ?)",
                  (telegram_id, papel, texto, _agora_txt()))
    _db().execute("""DELETE FROM historico WHERE telegram_id = ? AND id NOT IN (
                       SELECT id FROM historico WHERE telegram_id = ? ORDER BY id DESC LIMIT ?)""",
                  (telegram_id, telegram_id, MAX_HISTORICO))
    _db().commit()


def limpar_historico(telegram_id: str) -> None:
    _db().execute("DELETE FROM historico WHERE telegram_id = ?", (telegram_id,))
    _db().commit()


# --- planos (cardápio + lista de compras) ------------------------------------
def semana_atual() -> str:
    ano, semana, _ = agora().isocalendar()
    return f"{ano}-W{semana:02d}"


def salvar_plano(telegram_id: str, conteudo: dict) -> int:
    """Grava um plano novo (vira o atual) e mantém só os 3 últimos."""
    cur = _db().execute("INSERT INTO planos (telegram_id, semana, conteudo, criado_em) VALUES (?, ?, ?, ?)",
                        (telegram_id, conteudo.get("semana") or semana_atual(),
                         json.dumps(conteudo, ensure_ascii=False), _agora_txt()))
    _db().execute("""DELETE FROM planos WHERE telegram_id = ? AND id NOT IN (
                       SELECT id FROM planos WHERE telegram_id = ? ORDER BY id DESC LIMIT 3)""",
                  (telegram_id, telegram_id))
    _db().commit()
    return cur.lastrowid


def atualizar_plano(plano_id: int, conteudo: dict) -> None:
    """Muda o plano atual (troca de prato, receita guardada). Só quando a pessoa pede."""
    _db().execute("UPDATE planos SET conteudo = ? WHERE id = ?",
                  (json.dumps(conteudo, ensure_ascii=False), plano_id))
    _db().commit()


def planos(telegram_id: str, limite: int = 3) -> list[dict]:
    """Planos do mais novo para o mais antigo: [{"id", "semana", "criado_em", **conteudo}, ...]."""
    linhas = _db().execute("SELECT id, semana, conteudo, criado_em FROM planos WHERE telegram_id = ? "
                           "ORDER BY id DESC LIMIT ?", (telegram_id, limite)).fetchall()
    return [{**json.loads(l["conteudo"]), "id": l["id"], "semana": l["semana"], "criado_em": l["criado_em"]}
            for l in linhas]


def plano_atual(telegram_id: str) -> dict | None:
    encontrados = planos(telegram_id, 1)
    return encontrados[0] if encontrados else None


# --- limite diário de mensagens ----------------------------------------------
def mensagens_hoje(telegram_id: str) -> int:
    linha = _db().execute("SELECT mensagens FROM uso_diario WHERE telegram_id = ? AND dia = ?",
                          (telegram_id, hoje())).fetchone()
    return linha["mensagens"] if linha else 0


def contar_mensagem(telegram_id: str) -> None:
    _db().execute("""INSERT INTO uso_diario (telegram_id, dia, mensagens) VALUES (?, ?, 1)
                     ON CONFLICT (telegram_id, dia) DO UPDATE SET mensagens = mensagens + 1""",
                  (telegram_id, hoje()))
    _db().execute("DELETE FROM uso_diario WHERE dia < ?", ((agora().date() - timedelta(days=7)).isoformat(),))
    _db().commit()


# --- promoções ---------------------------------------------------------------
def adicionar_promocao(*, mercado: str, produto: str, preco: float, validade: str,
                       cidade: str | None, origem: str, **extras) -> int:
    colunas = {"mercado": mercado, "produto": produto, "preco": preco, "validade": validade,
               "cidade": cidade, "origem": origem, "criado_em": _agora_txt()}
    colunas.update({k: v for k, v in extras.items() if k in (
        "marca", "tamanho", "preco_anterior", "condicao", "validade_inicio", "lojas", "fonte_url")})
    cur = _db().execute(f"INSERT INTO promocoes ({', '.join(colunas)}) VALUES ({', '.join('?' * len(colunas))})",
                        tuple(colunas.values()))
    _db().commit()
    return cur.lastrowid


def promocoes_validas(cidade: str | None = None, mercado: str | None = None,
                      produto: str | None = None, limite: int = 50) -> list[dict]:
    """Ofertas que ainda valem hoje. Filtros por texto ignoram maiúsculas e acentos simples."""
    sql = "SELECT * FROM promocoes WHERE validade >= ?"
    parametros: list = [hoje()]
    for campo, valor in (("cidade", cidade), ("mercado", mercado), ("produto", produto)):
        if valor:
            sql += f" AND lower({campo}) LIKE ?"
            parametros.append(f"%{valor.strip().lower()}%")
    sql += " ORDER BY validade, preco LIMIT ?"
    parametros.append(limite)
    return [dict(l) for l in _db().execute(sql, parametros).fetchall()]


def promocao(promocao_id: int) -> dict | None:
    linha = _db().execute("SELECT * FROM promocoes WHERE id = ?", (promocao_id,)).fetchone()
    return dict(linha) if linha else None


def apagar_promocoes_vencidas() -> int:
    cur = _db().execute("DELETE FROM promocoes WHERE validade < ?", (hoje(),))
    _db().commit()
    return cur.rowcount


# --- preços vistos de verdade (Modo mercado, coletor) -------------------------
def adicionar_preco(*, produto: str, nome: str, preco: float, origem: str, embalagem: str | None = None,
                    tamanho: float | None = None, unidade: str | None = None, mercado: str | None = None,
                    cidade: str | None = None) -> int:
    cur = _db().execute("""INSERT INTO precos (produto, nome, embalagem, tamanho, unidade, preco, mercado, cidade,
                                               origem, criado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (produto, nome, embalagem, tamanho, unidade, preco, mercado, cidade, origem, _agora_txt()))
    _db().commit()
    return cur.lastrowid


def precos(produto: str | None = None, origem: str | None = None, limite: int = 50) -> list[dict]:
    """Preços mais recentes primeiro, filtrando por produto normalizado e/ou origem."""
    sql, parametros = "SELECT * FROM precos WHERE 1 = 1", []
    if produto:
        sql += " AND produto = ?"
        parametros.append(produto)
    if origem:
        sql += " AND origem = ?"
        parametros.append(origem)
    sql += " ORDER BY id DESC LIMIT ?"
    parametros.append(limite)
    return [dict(l) for l in _db().execute(sql, parametros).fetchall()]


# --- uso e custo das IAs -----------------------------------------------------
def registrar_uso_ia(*, provedor: str, nivel: str, modelo: str, tarefa: str, motivo: str,
                     tokens_entrada: int, tokens_saida: int, cache_leitura: int, cache_escrita: int,
                     custo_usd: float, cobrada: bool, escalonou_por: str | None) -> None:
    _db().execute("""INSERT INTO uso_ia (criado_em, dia, provedor, nivel, modelo, tarefa, motivo,
                       tokens_entrada, tokens_saida, cache_leitura, cache_escrita, custo_usd, cobrada, escalonou_por)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                  (_agora_txt(), hoje(), provedor, nivel, modelo, tarefa, motivo, tokens_entrada, tokens_saida,
                   cache_leitura, cache_escrita, custo_usd, int(cobrada), escalonou_por))
    _db().commit()


def chamadas_modelo_hoje(modelo: str) -> int:
    """Chamadas respondidas hoje por um modelo (é o que conta no limite diário)."""
    linha = _db().execute("SELECT COUNT(*) AS n FROM uso_ia WHERE modelo = ? AND dia = ? AND cobrada = 1",
                          (modelo, hoje())).fetchone()
    return linha["n"]


def resumo_custos(desde_dia: str) -> list[dict]:
    """Gasto por nível/modelo desde um dia (inclusive)."""
    linhas = _db().execute("""SELECT provedor, nivel, modelo, COUNT(*) AS chamadas,
                                     SUM(tokens_entrada) AS entrada, SUM(tokens_saida) AS saida,
                                     SUM(cache_leitura) AS cache_leitura, SUM(cache_escrita) AS cache_escrita,
                                     SUM(custo_usd) AS custo
                              FROM uso_ia WHERE dia >= ? AND cobrada = 1
                              GROUP BY provedor, nivel, modelo ORDER BY custo DESC""", (desde_dia,)).fetchall()
    return [dict(l) for l in linhas]


def resumo_escalonamentos(desde_dia: str) -> list[dict]:
    """Quantas vezes houve subida de nível, e por quê."""
    linhas = _db().execute("""SELECT escalonou_por AS motivo, COUNT(*) AS vezes FROM uso_ia
                              WHERE dia >= ? AND escalonou_por IS NOT NULL
                              GROUP BY escalonou_por ORDER BY vezes DESC""", (desde_dia,)).fetchall()
    return [dict(l) for l in linhas]


def resumo_cardapios(desde_dia: str) -> dict:
    """Cardápios gerados desde um dia: quantos, custo total e quantos precisaram do Opus.
    Cada cardápio começa numa chamada sem subida (escalonou_por vazio); as seguintes são subidas."""
    linha = _db().execute("""SELECT SUM(escalonou_por IS NULL) AS cardapios, SUM(custo_usd) AS custo,
                                    SUM(nivel = 'opus' AND cobrada = 1) AS com_opus
                             FROM uso_ia WHERE dia >= ? AND tarefa = 'cardapio'""", (desde_dia,)).fetchone()
    return {"cardapios": linha["cardapios"] or 0, "custo": linha["custo"] or 0.0, "com_opus": linha["com_opus"] or 0}


def chamadas_por_tarefa(desde_dia: str) -> list[dict]:
    """Qual modelo fez cada tarefa (para o /custos)."""
    linhas = _db().execute("""SELECT tarefa, nivel, COUNT(*) AS vezes, SUM(custo_usd) AS custo FROM uso_ia
                              WHERE dia >= ? AND cobrada = 1 GROUP BY tarefa, nivel ORDER BY tarefa, custo DESC""",
                           (desde_dia,)).fetchall()
    return [dict(l) for l in linhas]


def primeiro_dia_do_mes() -> str:
    d = agora().date()
    return date(d.year, d.month, 1).isoformat()
