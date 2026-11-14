#!/usr/bin/env python3
"""
Coletor oficial de dados do Radar Taubaté.
Extrai dados públicos da Câmara Municipal de Taubaté (Sistema SPL - Câmara Sem Papel):
https://camarasempapel.camarataubate.sp.gov.br/spl/

Regras de segurança (Passo 6 do Guia):
- Zero dependências externas (usa apenas biblioteca padrão do Python 3).
- Valida a integridade da coleta antes de sobrescrever dados.js: se a Câmara estiver
  fora do ar ou retornar dados incompletos, aborta com código de erro sem tocar no
  dados.js existente.
"""

import concurrent.futures
import csv
import datetime
import glob
import html
import http.cookiejar
import io
import json
import os
import re
import ssl
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
import zlib
from collections import Counter, defaultdict

SSL_CTX = ssl.create_default_context()
try:
    urllib.request.urlopen("https://camarasempapel.camarataubate.sp.gov.br/spl/parlamentares.aspx", timeout=10, context=SSL_CTX).close()
except Exception:
    SSL_CTX = ssl._create_unverified_context()

SPL_BASE = "https://camarasempapel.camarataubate.sp.gov.br/spl"
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

# Votos nominais nas eleições municipais de 2024 (TSE / Biografia oficial da Câmara)
VOTOS_2024_FALLBACK = {
    "36": 2536,  # Alberto Barreto
    "49": 2930,  # Ariel Katz
    "2":  2143,  # Bilili de Angelis
    "29": 1744,  # Boanerge
    "5":  5335,  # Diego Fonseca
    "9":  5160,  # Douglas Carbonne
    "50": 2400,  # Isaac do Carmo
    "28": 2359,  # Jessé Silva
    "25": 2049,  # João Henrique Dentinho
    "41": 4273,  # Moises Pirulito
    "17": 1688,  # Neneca Luiz Henrique
    "51": 1656,  # Nicola Neto
    "11": 1842,  # Nunes Coelho
    "42": 2670,  # Professor Edson
    "40": 2201,  # Richardson da Padaria
    "27": 3847,  # Rodson Lima Bobi
    "39": 4689,  # Talita
    "30": 2832,  # Vivi da Rádio
    "52": 1644,  # Zelinda Pastora
}

# Prestação de Contas Eleitorais e Histórico de Candidaturas (Fonte oficial: TSE Dados Abertos 2012–2026)
TSE_POR_PID = {
    "36": {
        "rec24": 34500.0, "gasto24": 34400.0, "gasto20": 3439.55,
        "outras": [{"ano": 2026, "cargo": "Deputado Estadual", "part": "PRD", "sit": "Suplente", "rec": 61830.0, "desp": 56961.0}],
        "hist": [
            {"ano": 2026, "cargo": "Deputado Estadual", "part": "PRD", "sit": "Suplente", "rec": 61830.0, "desp": 56961.0},
            {"ano": 2024, "cargo": "Vereador", "part": "PRD", "sit": "Eleito", "rec": 34500.0, "desp": 34400.0},
            {"ano": 2020, "cargo": "Vereador", "part": "PRTB", "sit": "Eleito", "rec": 4942.9, "desp": 3439.55},
        ],
    },
    "49": {
        "rec24": 10910.0, "gasto24": 10909.22, "gasto20": 0.0,
        "outras": [],
        "hist": [
            {"ano": 2024, "cargo": "Vereador", "part": "PDT", "sit": "Eleito", "rec": 10910.0, "desp": 10909.22},
        ],
    },
    "2": {
        "rec24": 75494.28, "gasto24": 75494.28, "gasto20": 49000.0,
        "outras": [{"ano": 2018, "cargo": "Deputado Estadual", "part": "PSDB", "sit": "Suplente", "rec": 226049.25, "desp": 219974.25}],
        "hist": [
            {"ano": 2024, "cargo": "Vereador", "part": "PP", "sit": "Eleito", "rec": 75494.28, "desp": 75494.28},
            {"ano": 2020, "cargo": "Vereador", "part": "PSDB", "sit": "Suplente", "rec": 49000.0, "desp": 49000.0},
            {"ano": 2018, "cargo": "Deputado Estadual", "part": "PSDB", "sit": "Suplente", "rec": 226049.25, "desp": 219974.25},
            {"ano": 2016, "cargo": "Vereador", "part": "PSDB", "sit": "Eleito", "rec": 0.0, "desp": 0.0},
            {"ano": 2012, "cargo": "Vereador", "part": "PSDB", "sit": "Eleito", "rec": 0.0, "desp": 0.0},
        ],
    },
    "29": {
        "rec24": 38003.2, "gasto24": 38003.2, "gasto20": 26370.03,
        "outras": [],
        "hist": [
            {"ano": 2024, "cargo": "Vereador", "part": "UNIÃO", "sit": "Eleito", "rec": 38003.2, "desp": 38003.2},
            {"ano": 2020, "cargo": "Vereador", "part": "PTB", "sit": "Eleito", "rec": 31523.46, "desp": 26370.03},
            {"ano": 2016, "cargo": "Vereador", "part": "PTB", "sit": "Eleito", "rec": 0.0, "desp": 0.0},
        ],
    },
    "5": {
        "rec24": 66450.0, "gasto24": 65958.0, "gasto20": 23097.59,
        "outras": [{"ano": 2018, "cargo": "Deputado Federal", "part": "PSDB", "sit": "Suplente", "rec": 99180.0, "desp": 88430.88}],
        "hist": [
            {"ano": 2024, "cargo": "Vereador", "part": "PL", "sit": "Eleito", "rec": 66450.0, "desp": 65958.0},
            {"ano": 2020, "cargo": "Vereador", "part": "PSDB", "sit": "Eleito", "rec": 29228.0, "desp": 23097.59},
            {"ano": 2018, "cargo": "Deputado Federal", "part": "PSDB", "sit": "Suplente", "rec": 99180.0, "desp": 88430.88},
            {"ano": 2016, "cargo": "Vereador", "part": "PSDB", "sit": "Eleito", "rec": 0.0, "desp": 0.0},
            {"ano": 2012, "cargo": "Vereador", "part": "PSDB", "sit": "Eleito", "rec": 0.0, "desp": 0.0},
        ],
    },
    "9": {
        "rec24": 39546.26, "gasto24": 28726.26, "gasto20": 20000.0,
        "outras": [
            {"ano": 2022, "cargo": "Deputado Estadual", "part": "REPUBLICANOS", "sit": "Suplente", "rec": 157999.0, "desp": 128113.8},
            {"ano": 2018, "cargo": "Deputado Estadual", "part": "PC do B", "sit": "Suplente", "rec": 89303.51, "desp": 82300.0},
            {"ano": 2014, "cargo": "Deputado Estadual", "part": "PC do B", "sit": "Suplente", "rec": 0.0, "desp": 0.0},
        ],
        "hist": [
            {"ano": 2024, "cargo": "Vereador", "part": "SOLIDARIEDADE", "sit": "Eleito", "rec": 39546.26, "desp": 28726.26},
            {"ano": 2022, "cargo": "Deputado Estadual", "part": "REPUBLICANOS", "sit": "Suplente", "rec": 157999.0, "desp": 128113.8},
            {"ano": 2020, "cargo": "Vereador", "part": "DEM", "sit": "Eleito", "rec": 22000.0, "desp": 20000.0},
            {"ano": 2018, "cargo": "Deputado Estadual", "part": "PC do B", "sit": "Suplente", "rec": 89303.51, "desp": 82300.0},
            {"ano": 2016, "cargo": "Vereador", "part": "PC do B", "sit": "Eleito", "rec": 0.0, "desp": 0.0},
            {"ano": 2014, "cargo": "Deputado Estadual", "part": "PC do B", "sit": "Suplente", "rec": 0.0, "desp": 0.0},
            {"ano": 2012, "cargo": "Vereador", "part": "PC do B", "sit": "Eleito", "rec": 0.0, "desp": 0.0},
        ],
    },
    "50": {
        "rec24": 67145.16, "gasto24": 67180.0, "gasto20": 0.0,
        "outras": [
            {"ano": 2016, "cargo": "Prefeito", "part": "PT", "sit": "Não Eleito", "rec": 0.0, "desp": 0.0},
            {"ano": 2014, "cargo": "Deputado Estadual", "part": "PT", "sit": "Suplente", "rec": 0.0, "desp": 0.0},
            {"ano": 2012, "cargo": "Prefeito", "part": "PT", "sit": "2º Turno", "rec": 0.0, "desp": 0.0},
        ],
        "hist": [
            {"ano": 2024, "cargo": "Vereador", "part": "PT", "sit": "Eleito", "rec": 67145.16, "desp": 67180.0},
            {"ano": 2016, "cargo": "Prefeito", "part": "PT", "sit": "Não Eleito", "rec": 0.0, "desp": 0.0},
            {"ano": 2014, "cargo": "Deputado Estadual", "part": "PT", "sit": "Suplente", "rec": 0.0, "desp": 0.0},
            {"ano": 2012, "cargo": "Prefeito", "part": "PT", "sit": "2º Turno", "rec": 0.0, "desp": 0.0},
        ],
    },
    "28": {
        "rec24": 5000.0, "gasto24": 4999.15, "gasto20": 8750.0,
        "outras": [],
        "hist": [
            {"ano": 2024, "cargo": "Vereador", "part": "PODE", "sit": "Eleito", "rec": 5000.0, "desp": 4999.15},
            {"ano": 2020, "cargo": "Vereador", "part": "PL", "sit": "Eleito", "rec": 8750.0, "desp": 8750.0},
            {"ano": 2016, "cargo": "Vereador", "part": "SD", "sit": "Eleito", "rec": 0.0, "desp": 0.0},
            {"ano": 2012, "cargo": "Vereador", "part": "PSL", "sit": "Suplente", "rec": 0.0, "desp": 0.0},
        ],
    },
    "25": {
        "rec24": 31740.0, "gasto24": 24340.0, "gasto20": 8000.0,
        "outras": [],
        "hist": [
            {"ano": 2024, "cargo": "Vereador", "part": "PP", "sit": "Eleito", "rec": 31740.0, "desp": 24340.0},
            {"ano": 2020, "cargo": "Vereador", "part": "PSL", "sit": "Eleito", "rec": 8750.0, "desp": 8000.0},
            {"ano": 2016, "cargo": "Vereador", "part": "PV", "sit": "Eleito", "rec": 0.0, "desp": 0.0},
            {"ano": 2012, "cargo": "Vereador", "part": "PSB", "sit": "Suplente", "rec": 0.0, "desp": 0.0},
        ],
    },
    "41": {
        "rec24": 65450.0, "gasto24": 64995.0, "gasto20": 28750.0,
        "outras": [{"ano": 2026, "cargo": "Deputado Estadual", "part": "PODE", "sit": "Suplente", "rec": 109104.27, "desp": 88305.96}],
        "hist": [
            {"ano": 2026, "cargo": "Deputado Estadual", "part": "PODE", "sit": "Suplente", "rec": 109104.27, "desp": 88305.96},
            {"ano": 2024, "cargo": "Vereador", "part": "PL", "sit": "Eleito", "rec": 65450.0, "desp": 64995.0},
            {"ano": 2020, "cargo": "Vereador", "part": "PL", "sit": "Eleito", "rec": 32350.0, "desp": 28750.0},
            {"ano": 2016, "cargo": "Vereador", "part": "PPS", "sit": "Suplente", "rec": 0.0, "desp": 0.0},
            {"ano": 2012, "cargo": "Vereador", "part": "PSDC", "sit": "Suplente", "rec": 0.0, "desp": 0.0},
        ],
    },
    "17": {
        "rec24": 17600.0, "gasto24": 17600.0, "gasto20": 18401.8,
        "outras": [],
        "hist": [
            {"ano": 2024, "cargo": "Vereador", "part": "PDT", "sit": "Eleito", "rec": 17600.0, "desp": 17600.0},
            {"ano": 2020, "cargo": "Vereador", "part": "PDT", "sit": "Eleito", "rec": 18401.8, "desp": 18401.8},
            {"ano": 2016, "cargo": "Vereador", "part": "PDT", "sit": "Eleito", "rec": 0.0, "desp": 0.0},
            {"ano": 2012, "cargo": "Vereador", "part": "PDT", "sit": "Eleito", "rec": 0.0, "desp": 0.0},
        ],
    },
    "51": {
        "rec24": 17345.85, "gasto24": 17345.85, "gasto20": 0.0,
        "outras": [],
        "hist": [
            {"ano": 2024, "cargo": "Vereador", "part": "NOVO", "sit": "Eleito", "rec": 17345.85, "desp": 17345.85},
        ],
    },
    "11": {
        "rec24": 105000.0, "gasto24": 96804.53, "gasto20": 25315.85,
        "outras": [],
        "hist": [
            {"ano": 2024, "cargo": "Vereador", "part": "REPUBLICANOS", "sit": "Eleito", "rec": 105000.0, "desp": 96804.53},
            {"ano": 2020, "cargo": "Vereador", "part": "REPUBLICANOS", "sit": "Eleito", "rec": 35940.0, "desp": 25315.85},
            {"ano": 2016, "cargo": "Vereador", "part": "PRB", "sit": "Eleito", "rec": 0.0, "desp": 0.0},
            {"ano": 2012, "cargo": "Vereador", "part": "PRB", "sit": "Eleito", "rec": 0.0, "desp": 0.0},
        ],
    },
    "42": {
        "rec24": 24684.73, "gasto24": 24684.73, "gasto20": 13000.0,
        "outras": [
            {"ano": 2016, "cargo": "Vice-Prefeito", "part": "PSD", "sit": "Eleito", "rec": 0.0, "desp": 0.0},
            {"ano": 2012, "cargo": "Vice-Prefeito", "part": "PSDB", "sit": "Eleito", "rec": 0.0, "desp": 0.0},
        ],
        "hist": [
            {"ano": 2024, "cargo": "Vereador", "part": "PSD", "sit": "Eleito", "rec": 24684.73, "desp": 24684.73},
            {"ano": 2020, "cargo": "Vereador", "part": "PSD", "sit": "Eleito", "rec": 13000.0, "desp": 13000.0},
            {"ano": 2016, "cargo": "Vice-Prefeito", "part": "PSD", "sit": "Eleito", "rec": 0.0, "desp": 0.0},
            {"ano": 2012, "cargo": "Vice-Prefeito", "part": "PSDB", "sit": "Eleito", "rec": 0.0, "desp": 0.0},
        ],
    },
    "40": {
        "rec24": 29272.3, "gasto24": 29272.3, "gasto20": 6808.75,
        "outras": [{"ano": 2026, "cargo": "Deputado Federal", "part": "UNIÃO", "sit": "Suplente", "rec": 208866.35, "desp": 190920.76}],
        "hist": [
            {"ano": 2026, "cargo": "Deputado Federal", "part": "UNIÃO", "sit": "Suplente", "rec": 208866.35, "desp": 190920.76},
            {"ano": 2024, "cargo": "Vereador", "part": "UNIÃO", "sit": "Eleito", "rec": 29272.3, "desp": 29272.3},
            {"ano": 2020, "cargo": "Vereador", "part": "DEM", "sit": "Eleito", "rec": 6808.75, "desp": 6808.75},
            {"ano": 2016, "cargo": "Vereador", "part": "PPS", "sit": "Suplente", "rec": 0.0, "desp": 0.0},
        ],
    },
    "27": {
        "rec24": 68931.8, "gasto24": 68481.8, "gasto20": 9533.0,
        "outras": [],
        "hist": [
            {"ano": 2024, "cargo": "Vereador", "part": "PRD", "sit": "Eleito", "rec": 68931.8, "desp": 68481.8},
            {"ano": 2020, "cargo": "Vereador", "part": "PSDB", "sit": "Eleito", "rec": 9533.0, "desp": 9533.0},
            {"ano": 2016, "cargo": "Vereador", "part": "PV", "sit": "Eleito", "rec": 0.0, "desp": 0.0},
            {"ano": 2012, "cargo": "Vereador", "part": "PP", "sit": "Suplente", "rec": 0.0, "desp": 0.0},
        ],
    },
    "39": {
        "rec24": 55527.87, "gasto24": 44337.75, "gasto20": 950.0,
        "outras": [
            {"ano": 2026, "cargo": "Deputada Estadual", "part": "PSB", "sit": "Suplente", "rec": 364483.43, "desp": 358868.38},
            {"ano": 2022, "cargo": "Deputada Estadual", "part": "PSB", "sit": "Suplente", "rec": 121961.31, "desp": 108499.06},
        ],
        "hist": [
            {"ano": 2026, "cargo": "Deputada Estadual", "part": "PSB", "sit": "Suplente", "rec": 364483.43, "desp": 358868.38},
            {"ano": 2024, "cargo": "Vereadora", "part": "PSB", "sit": "Eleita", "rec": 55527.87, "desp": 44337.75},
            {"ano": 2022, "cargo": "Deputada Estadual", "part": "PSB", "sit": "Suplente", "rec": 121961.31, "desp": 108499.06},
            {"ano": 2020, "cargo": "Vereadora", "part": "PSB", "sit": "Eleita", "rec": 950.0, "desp": 950.0},
        ],
    },
    "30": {
        "rec24": 41000.0, "gasto24": 41100.0, "gasto20": 18851.65,
        "outras": [{"ano": 2026, "cargo": "Deputada Federal", "part": "REPUBLICANOS", "sit": "Suplente", "rec": 663898.77, "desp": 606816.5}],
        "hist": [
            {"ano": 2026, "cargo": "Deputada Federal", "part": "REPUBLICANOS", "sit": "Suplente", "rec": 663898.77, "desp": 606816.5},
            {"ano": 2024, "cargo": "Vereadora", "part": "REPUBLICANOS", "sit": "Eleita", "rec": 41000.0, "desp": 41100.0},
            {"ano": 2020, "cargo": "Vereadora", "part": "REPUBLICANOS", "sit": "Eleita", "rec": 28513.65, "desp": 18851.65},
            {"ano": 2016, "cargo": "Vereadora", "part": "PSC", "sit": "Eleita", "rec": 0.0, "desp": 0.0},
        ],
    },
    "52": {
        "rec24": 53990.3, "gasto24": 42737.9, "gasto20": 0.0,
        "outras": [{"ano": 2026, "cargo": "Deputada Federal", "part": "PRD", "sit": "Suplente", "rec": 562452.5, "desp": 550000.0}],
        "hist": [
            {"ano": 2026, "cargo": "Deputada Federal", "part": "PRD", "sit": "Suplente", "rec": 562452.5, "desp": 550000.0},
            {"ano": 2024, "cargo": "Vereadora", "part": "PRD", "sit": "Eleita", "rec": 53990.3, "desp": 42737.9},
        ],
    },
}

TSE_PREFEITO = {
    "rec24": 1155162.47,
    "gasto24": 1179697.31,
    "cpv24": 12.11,
    "outras": [
        {"ano": 2022, "cargo": "Deputado Estadual", "part": "NOVO", "sit": "Suplente", "rec": 458182.09, "desp": 442352.75},
        {"ano": 2018, "cargo": "Deputado Estadual", "part": "NOVO", "sit": "Eleito", "rec": 37520.0, "desp": 37304.48},
    ],
    "hist": [
        {"ano": 2024, "cargo": "Prefeito", "part": "NOVO", "sit": "Eleito (2º Turno)", "rec": 1155162.47, "desp": 1179697.31},
        {"ano": 2022, "cargo": "Deputado Estadual", "part": "NOVO", "sit": "Suplente", "rec": 458182.09, "desp": 442352.75},
        {"ano": 2018, "cargo": "Deputado Estadual", "part": "NOVO", "sit": "Eleito", "rec": 37520.0, "desp": 37304.48},
    ],
}

BAIRROS_TAUBATE = [
    "Barreiro", "Gurilândia", "Quiririm", "São Gonçalo", "Independência",
    "Continental", "Cecap", "Estiva", "Santa Tereza", "Bonfim",
    "Marlene Miranda", "Chácara Silvestre", "Belém", "Areão", "Vila São Geraldo",
    "Vila São José", "Estoril", "Pinheirinho", "Sítio Santo Antônio", "Sete Voltas",
    "Parque Três Marias", "Imaculada", "Jardim do Lago", "Jardim das Nações", "Jaraguá",
    "Parque Aeroporto", "Parque São Luís", "Esplanada Independência", "Cataguá", "Água Quente",
    "Itaim", "Jardim Maria Augusta", "Parque Urupês", "Portal da Mantiqueira", "Terra Nova",
    "Fonte Imaculada", "Monjolinho", "Mourisco", "Jardim Santa Clara", "Parque Sabará",
    "Alto São Pedro", "Chácara Ingrid", "Jardim Ana Rosa", "Parque Ipanema", "Vila Aparecida",
    "Registro", "Berta Grande", "Barranco", "Parque Senhor do Bonfim", "Jardim Califórnia",
    "Jardim Baronesa", "Vila Edmundo", "Vila Marli", "Chácara Flórida", "Pedra Branca",
    "Santa Fé", "Bosque da Saúde", "Jardim Morumbi", "Jardim América", "Jardim Paulista",
    "Vila Costa", "Jardim Oásis", "Parque Piratininga", "Parque Santo Antônio"
]

TH_RULES = [
    ("luz", r"iluminac|lampad|poste|led|escuro|escurid|brac[oa]s? de luz|rede de energia"),
    ("asf", r"tapa[- ]?burac|buraco|recapea|asfalto|pavimenta|massa asfaltica|cratera|desnivelad|cascalha|patrolamento|nivelamento"),
    ("tra", r"lombada|redutor de velocidade|semaforo|faixa de pedestre|sinalizac|transito|rotatoria|radar|travessia elevada|ombro|mao unica|estacionamento|botoeira"),
    ("agu", r"esgoto|bueiro|boca de lobo|alagament|drenagem|galeria pluvial|enchent|vazamento|sabesp|agua parada|canaleta"),
    ("lim", r"mato alto|capina|rocada|limpeza|entulho|lixo|cacamba|descarte irregular|poda|arvore|varricao|terreno baldio|zeladoria"),
    ("cal", r"calcada|meio[- ]?fio|guia|sarjeta|acessibilidade|rampa|passarela"),
    ("sau", r"\bubs\b|\besf\b|\bpamo\b|\bupa\b|hmut|hospital|posto de saude|medicament|remedio|medico|consulta|exame|dengue|zoonose|vacina|ambulancia|samu|saude|cirurgia"),
    ("edu", r"escola|creche|emei|emef|merenda|aluno|professor|uniforme|educac|quadra escolar"),
    ("seg", r"seguranca|guarda civil|\bgcm\b|policia|ronda|patrulha|camera de monitoramento|\bcoi\b|assalto|furto|violencia"),
    ("bus", r"onibus|ponto de onibus|abrigo de onibus|transporte publico|\babc\b|tctau|linha de onibus|itinerario|rodoviari"),
    ("laz", r"parque|quadra|campo de futebol|academia ao ar livre|playground|brinquedo|pista de caminhada|area de lazer|esportiv|revitalizac.*praca|reforma.*praca|manutencao.*praca"),
]

THH_RULES = [
    ("pes", r"pesar|falecimento|luto|condolenc|in memoriam"),
    ("tit", r"cidadao taubateano|cidada taubateana|titulo de cidada|medalha|comenda|honra ao merito|diploma de honra|utilidade publica|patrimonio cultural"),
    ("nom", r"denomina|denominac|nome de rua|logradouro"),
    ("dat", r"calendario oficial|institui o dia|institui a semana|dia municipal|semana municipal"),
    ("par", r"aplauso|congratulac|parabeniz|louvor|homenage|solenidade"),
]

TIPO_ABBR = {
    "Requerimento": "REQ",
    "Indicação": "IND",
    "Moção": "MOC",
    "Projeto de Lei Ordinária": "PL",
    "Projeto de Lei Complementar": "PLC",
    "Projeto de Decreto Legislativo": "PDL",
    "Projeto de Resolução": "PRE",
    "Proposta de Emenda à Lei Orgânica do Município": "PEL",
    "Emenda": "Emenda",
    "Substitutivo": "Substitutivo",
    "Frente Parlamentar": "FRP",
    "Nome Parlamentar": "NPA",
}

STREET_PAT = re.compile(
    r"\b((?:Rua|Avenida|Av\.|Estrada(?:\s+Municipal)?|Praça|Travessa|Alameda|Rodovia|Viela)\s+[A-ZÀ-Ú0-9][A-Za-zÀ-ÿ0-9\s\.\'\-]{3,65}?)(?=\s*(?:,|\bnº|\bn\.|\bno\s+bairro|\bna\s+região|\bbairro\b|\s-\s|\s–\s|\.|\)|;|\bonde\b|\bque\b|\bpara\b|\bem\s+frente\b|\bpróximo\b|\besquina\b|\bcruzamento\b|$))",
    re.I,
)


def norm(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", (s or "").lower())
        if unicodedata.category(c) != "Mn"
    )


def http_get(url: str, timeout: int = 30) -> bytes:
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (RadarTaubate/1.0)"})
            return urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX).read()
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))
    return b""


def classify_theme(grupo: str, txt: str) -> str:
    nt = norm(txt)
    if grupo == "h":
        for code, pat in THH_RULES:
            if re.search(pat, nt):
                return code
        return "par"
    elif grupo in ("b", "c"):
        for code, pat in TH_RULES:
            if re.search(pat, nt):
                return code
        return ""
    return ""


def classify_item(tipo: str, ementa: str):
    nt = norm(ementa)
    eh_materia = 1

    if tipo == "Indicação":
        grupo = "b"
    elif tipo == "Requerimento":
        if re.search(r"justificativa de ausencia|retirada d[eo] projeto|retirada d[ae] proposi|licenca|destaque|regime de urgencia|adiamento|arquivamento|pedido de vista|uso da tribuna", nt):
            grupo = "o"
        elif re.search(r"solenidade|sessao solene|homenage|voto de louvor|congratulac|aplauso", nt):
            grupo = "h"
        elif re.search(r"informa|esclarec|audiencia|copia|cronograma|convoca|prestacao|relatorio|quantos|quais|motivo|por que|previsao|situacao|fiscaliza", nt):
            grupo = "c"
        else:
            grupo = "b"
    elif tipo == "Moção":
        if re.search(r"apelo|repudio", nt):
            grupo = "c"
        elif re.search(r"apoio", nt) and not re.search(r"aplauso|congratul|pesar", nt):
            grupo = "o"
        else:
            grupo = "h"
    elif tipo == "Projeto de Decreto Legislativo":
        if re.search(r"cidada|titulo|medalha|homenage|solenidade|honra|comenda|denom", nt):
            grupo = "h"
        else:
            grupo = "o"
    elif tipo in ("Projeto de Resolução", "Frente Parlamentar", "Nome Parlamentar", "Emenda", "Substitutivo"):
        grupo = "o"
    elif tipo in ("Projeto de Lei Ordinária", "Projeto de Lei Complementar", "Proposta de Emenda à Lei Orgânica do Município"):
        if re.search(r"denomina|calendario oficial|institui o dia|institui a semana|dia municipal|semana municipal|utilidade publica|patrimonio cultural|homenage", nt):
            grupo = "h"
        else:
            grupo = "l"
    else:
        grupo = "o"

    th = classify_theme(grupo, ementa)
    return grupo, eh_materia, th


def parse_csv_content(raw_text: str):
    lines = raw_text.splitlines()
    joined = []
    for line in lines:
        if not line.strip():
            continue
        if line.startswith("ID,Processo,Ano,") or re.match(r"^\d+,\d+,\d{4},", line):
            joined.append(line)
        elif joined:
            joined[-1] = joined[-1] + " " + line.strip()
    rows = []
    for i, r in enumerate(csv.reader(io.StringIO("\n".join(joined)))):
        if i == 0 or len(r) < 14:
            continue
        if not re.match(r"^\d{2}/\d{2}/\d{4}$", r[-5].strip()):
            continue
        rows.append({
            "id": r[0].strip(),
            "proc": r[1].strip(),
            "ano_proc": r[2].strip(),
            "tipo": r[3].strip(),
            "num": r[4].strip(),
            "ano": r[5].strip(),
            "ementa": ", ".join(r[6:-7]).strip().strip('"').strip(),
            "protocolo": r[-7].strip(),
            "autor": r[-6].strip(),
            "data": r[-5].strip(),
            "fase": r[-4].strip(),
            "setor": r[-3].strip(),
            "arq_setor": r[-2].strip(),
            "situacao": r[-1].strip(),
        })
    return rows


def fetch_csv_from_spl(url: str) -> str:
    for attempt in range(3):
        try:
            cj = http.cookiejar.CookieJar()
            opener = urllib.request.build_opener(
                urllib.request.HTTPCookieProcessor(cj),
                urllib.request.HTTPSHandler(context=SSL_CTX),
            )
            opener.addheaders = [("User-Agent", "Mozilla/5.0 (RadarTaubate/1.0)")]
            page_html = opener.open(url, timeout=30).read().decode("utf-8", errors="ignore")
            m_vs = re.search(r'id="__VIEWSTATE" value="([^"]*)"', page_html)
            if not m_vs:
                return ""
            vs = m_vs.group(1)
            vsg = re.search(r'id="__VIEWSTATEGENERATOR" value="([^"]*)"', page_html).group(1)
            ev = re.search(r'id="__EVENTVALIDATION" value="([^"]*)"', page_html).group(1)
            data = urllib.parse.urlencode({
                "__VIEWSTATE": vs,
                "__VIEWSTATEGENERATOR": vsg,
                "__EVENTVALIDATION": ev,
                "ctl00$ContentPlaceHolder1$btn_export_csv": "CSV",
            }).encode("utf-8")
            resp = opener.open(url, data=data, timeout=60)
            ctype = resp.headers.get("Content-Type", "")
            if "CSV" not in ctype.upper():
                return ""
            return resp.read().decode("latin1", errors="replace")
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))
    return ""


def parse_pdf_votes(raw_pdf: bytes, sid: str, dt_iso: str, purl: str):
    votes = []
    streams = re.findall(rb"stream\r?\n(.*?)\r?\nendstream", raw_pdf, re.S)
    for st in streams:
        try:
            dec = zlib.decompress(st).decode("latin1")
        except Exception:
            continue
        tokens = [
            t.replace(r"\(", "(").replace(r"\)", ")").strip()
            for t in re.findall(r"\((.*?)\)Tj", dec)
            if t.strip()
        ]
        if not tokens or not any(k in tokens[0] for k in ("Relatório de Votação", "Lista de votação")):
            continue
        if "Parlamentar" not in tokens or "Totais:" not in tokens:
            continue
        sess_name = tokens[2] if len(tokens) > 2 else ""
        prop_title = tokens[3] if len(tokens) > 3 else ""
        turno = tokens[4] if len(tokens) > 4 else ""
        idx_nom = tokens.index("Nominal") if "Nominal" in tokens else 11
        idx_parl = tokens.index("Parlamentar")
        idx_hora = tokens.index("Hora")
        idx_tot = tokens.index("Totais:")

        meta_tokens = tokens[idx_nom + 1 : idx_parl]
        autoria = ""
        ementa_parts = []
        for mt in meta_tokens:
            if mt.startswith("Autoria:"):
                autoria = mt.replace("Autoria:", "").strip()
            else:
                ementa_parts.append(mt)
        ementa = " ".join(ementa_parts).strip()

        votos_parl = {}
        i = idx_hora + 1
        while i < idx_tot:
            tk = tokens[i]
            m_p = re.match(r"^([A-ZÀ-Ú0-9\s\.\-]+?)\s*\(([^)]+)\)$", tk)
            if m_p and i + 1 < idx_tot:
                pname = m_p.group(1).strip()
                voto = tokens[i + 1].strip()
                votos_parl[pname] = voto
                i += 2
                if i < idx_tot and re.match(r"^\d{2}:\d{2}:\d{2}$", tokens[i]):
                    i += 1
            else:
                i += 1

        resultado = ""
        if "Resultado:" in tokens:
            ir = tokens.index("Resultado:")
            if ir > 0:
                resultado = tokens[ir - 1]

        votes.append({
            "sid": sid,
            "data": dt_iso,
            "sess_name": sess_name,
            "prop_title": prop_title,
            "turno": turno,
            "autoria": autoria,
            "ementa": ementa,
            "resultado": resultado,
            "url": purl,
            "votos": votos_parl,
        })
    return votes


def collect_live(scratch_dir: str):
    """Coleta 100% online diretamente do SPL da Câmara Municipal de Taubaté."""
    os.makedirs(scratch_dir, exist_ok=True)
    os.makedirs(os.path.join(scratch_dir, "csv"), exist_ok=True)
    os.makedirs(os.path.join(scratch_dir, "pdfs"), exist_ok=True)
    for old_csv in glob.glob(os.path.join(scratch_dir, "csv", "*.csv")):
        try:
            os.remove(old_csv)
        except OSError:
            pass

    # 1. Mapear autores em consulta-autor.aspx
    h_autor = http_get(f"{SPL_BASE}/consulta-autor.aspx").decode("utf-8", errors="ignore")
    autor_map = {}
    for m in re.finditer(r"card-title[^>]*>(.*?)</div>.*?consulta-producao\.aspx\?autor=(\d+)", h_autor, re.S):
        name = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        name = re.sub(r"\(\d+\)$", "", name).strip()
        autor_map[name.lower()] = m.group(2)

    # 2. Listar vereadores titulares em parlamentares.aspx (apenas bloco 'Ativos', ignorando Suplentes / Ex-suplentes)
    h_parl = http_get(f"{SPL_BASE}/parlamentares.aspx").decode("utf-8", errors="ignore")
    main_part = re.split(r"(?:Suplentes\s+em\s+Exerc[ií]cio|Ex-suplentes|Suplentes|Licenciados|Inativos)", h_parl, maxsplit=1, flags=re.I)[0]
    pids = []
    for m in re.finditer(r"parlamentar\.aspx\?id=(\d+)", main_part):
        if m.group(1) not in pids:
            pids.append(m.group(1))

    cur_year = datetime.date.today().year
    years = [str(y) for y in range(2025, cur_year + 1)]

    def fetch_one_vereador(pid: str):
        url = f"{SPL_BASE}/parlamentar.aspx?id={pid}"
        phtml = http_get(url).decode("utf-8", errors="ignore")
        ap_m = (
            re.search(r'id="nome_parlamentar"[^>]*>(.*?)</div>', phtml, re.S)
            or re.search(r"<a href='#' class='kt-widget__title'>(.*?)</a>", phtml, re.S)
        )
        ap = html.unescape(re.sub(r"<[^>]+>", "", ap_m.group(1)).strip()) if ap_m else ""

        part_m = (
            re.search(r'id="partido"[^>]*>(.*?)</span>', phtml, re.S)
            or re.search(r"<b>Partido:\s*</b>([^<]+)", phtml)
        )
        part_raw = html.unescape(re.sub(r"<[^>]+>", "", part_m.group(1)).strip()) if part_m else ""
        part_paren = re.search(r"\(([^)]+)\)", part_raw)
        part = part_paren.group(1).strip() if part_paren else part_raw

        leg19_block = phtml.split("18ª Legislatura")[0] if "18ª Legislatura" in phtml else phtml
        mesa_m = re.search(r"Participação na Mesa Diretora.*?<strong[^>]*>(.*?)</strong>", leg19_block, re.S)
        if mesa_m:
            mesa_raw = html.unescape(re.sub(r"<[^>]+>", " ", mesa_m.group(1)).strip())
        else:
            desc_m = re.search(r"<span class='kt-widget__desc'>(.*?)</span>", phtml, re.S)
            mesa_raw = html.unescape(re.sub(r"<[^>]+>", " ", desc_m.group(1)).strip()) if desc_m else ""

        def get_info(label):
            m = re.search(rf"kt-widget__label'>\s*{label}:\s*</span>\s*<span[^>]*>(.*?)</span>", phtml, re.S)
            return html.unescape(re.sub(r"<[^>]+>", "", m.group(1)).strip()) if m else ""

        nome_civil = get_info("Nome civil")
        tel = get_info(r"Telefone\(s\)")
        cel = get_info(r"Celular(?:\(es\))?")
        email = get_info("E-mail")

        bio_m = (
            re.search(r'id="texto_biografia"[^>]*>(.*?)<div class="kt-timeline', phtml, re.S)
            or re.search(r"Biografia Parlamentar\s*</h3>.*?<div class=\"kt-widget12__info\">(.*?)</div>", phtml, re.S)
        )
        bio = html.unescape(re.sub(r"<[^>]+>", " ", bio_m.group(1)).strip()) if bio_m else ""

        # Extrair legislaturas (mandatos)
        legislaturas = []
        seen_legs = set()
        for rm in re.finditer(r"title=['\"](\d+ª Legislatura)\s*\((\d{2}/\d{2}/\d{4})\s*a\s*(\d{2}/\d{2}/\d{4})\)['\"]", phtml):
            leg, ini_l, fim_l = rm.group(1).strip(), rm.group(2).strip(), rm.group(3).strip()
            if leg not in seen_legs:
                seen_legs.add(leg)
                legislaturas.append({"leg": leg, "ini": ini_l, "fim": fim_l})
        if not legislaturas:
            mand_m = re.search(r'id="mandatos_html"(.*?)</table>', phtml, re.S)
            if mand_m:
                for rm in re.finditer(r"<tr>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*</tr>", mand_m.group(1), re.S):
                    leg = html.unescape(re.sub(r"<[^>]+>", "", rm.group(1)).strip())
                    ini_l = html.unescape(re.sub(r"<[^>]+>", "", rm.group(2)).strip())
                    fim_l = html.unescape(re.sub(r"<[^>]+>", "", rm.group(3)).strip())
                    if leg not in seen_legs:
                        seen_legs.add(leg)
                        legislaturas.append({"leg": leg, "ini": ini_l, "fim": fim_l})

        # Extrair comissões atuais (2025/2026)
        comissoes = []
        for cm in re.finditer(r"Cargo:\s*([^\(<]+)\(([^)]+)\)\s*</h3>\s*<span[^>]*>.*?<a[^>]*>(.*?)</a>", leg19_block, re.S):
            c_cargo = html.unescape(cm.group(1).strip())
            c_per = html.unescape(cm.group(2).strip())
            c_nome = html.unescape(re.sub(r"<[^>]+>", "", cm.group(3)).strip())
            c_nome = re.sub(r"\s*-\s*\d+ª\s*Formação.*$", "", c_nome, flags=re.I).strip()
            if "2026" in c_per or "2025" in c_per:
                comissoes.append({"cargo": c_cargo, "nome": c_nome})
        if not comissoes:
            com_m = re.search(r'id="comissoes_html"(.*?)</table>', phtml, re.S)
            if com_m:
                for rm in re.finditer(r"<tr>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*</tr>", com_m.group(1), re.S):
                    c_cargo = html.unescape(re.sub(r"<[^>]+>", "", rm.group(1)).strip())
                    c_nome = html.unescape(re.sub(r"<[^>]+>", "", rm.group(2)).strip())
                    c_ini = html.unescape(re.sub(r"<[^>]+>", "", rm.group(3)).strip())
                    c_fim = html.unescape(re.sub(r"<[^>]+>", "", rm.group(4)).strip())
                    if "2026" in c_fim or "2025" in c_ini:
                        comissoes.append({"cargo": c_cargo, "nome": c_nome})

        # Extrair Emendas Impositivas da biografia
        emendas_imp = []
        for em in re.finditer(r"<a[^>]+href=['\"]([^'\"]+)['\"][^>]*>\s*(202\d)\s*</a>", phtml, re.I):
            u_em = em.group(1)
            if not u_em.startswith("http"):
                u_em = "https://camarasempapel.camarataubate.sp.gov.br/" + u_em.lstrip("/")
            emendas_imp.append({"ano": em.group(2), "url": u_em})

        # Extrair Leis promulgadas (direto da aba tab_leis_autoria ou fallback em consulta-legislacao.aspx)
        leis_count = {}
        if 'id="tab_leis_autoria"' in phtml:
            leis_tab = phtml.split('id="tab_leis_autoria"')[1].split('id="tab_frequencia_plenario"')[0]
            for lm in re.finditer(r"(Lei Ordinária|Lei Complementar|Decreto Legislativo|Emenda à Lei Orgânica|Resolução)\s*<span[^>]*>(\d+)</span>", leis_tab, re.S):
                leis_count[lm.group(1)] = int(lm.group(2))
        if not leis_count:
            try:
                leg_url = f"https://camarasempapel.camarataubate.sp.gov.br/legislacao/consulta-legislacao.aspx?autor={pid}"
                lhtml = http_get(leg_url).decode("utf-8", errors="ignore")
                for lm in re.finditer(r"(Lei Ordinária|Lei Complementar|Decreto Legislativo|Emenda à Lei Orgânica|Resolução)\s*n[º°]", lhtml):
                    lt = lm.group(1)
                    leis_count[lt] = leis_count.get(lt, 0) + 1
            except Exception:
                pass

        freq = {}
        if 'id="tab_frequencia_plenario"' in phtml:
            f_sub = phtml.split('id="tab_frequencia_plenario"')[1]
            for fm in re.finditer(r"<h3 class=['\"]kt-widget1__title['\"]>(.*?)</h3>(.*?)(?=<div class=['\"]kt-widget1__item['\"]|</div>\s*</div>\s*</div>)", f_sub, re.S):
                status_name = html.unescape(re.sub(r"<[^>]+>", "", fm.group(1)).strip())
                yr_pairs = dict(re.findall(r"<big[^>]*>(\d{4})</big>\s*<span[^>]*>(\d+)</span>", fm.group(2)))
                freq[status_name] = {
                    "2026": int(yr_pairs.get("2026", 0)),
                    "2025": int(yr_pairs.get("2025", 0)),
                }

        aid_m = re.search(r"consulta-producao\.aspx\?tipo=\d+&(?:amp;)?autor=(\d+)", phtml)
        aid = aid_m.group(1) if aid_m else autor_map.get(ap.lower(), pid)
        for ano in years:
            u_csv = f"{SPL_BASE}/consulta-producao.aspx?autor={aid}&ano={ano}"
            raw_csv = fetch_csv_from_spl(u_csv)
            if raw_csv:
                with open(os.path.join(scratch_dir, "csv", f"autor_{aid}_{ano}.csv"), "w", encoding="utf-8") as out:
                    out.write(raw_csv)
            else:
                # Fallback por tipo caso passe de 1000 registros no ano
                combined = []
                for t_id in [1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 130, 201]:
                    sub_csv = fetch_csv_from_spl(f"{SPL_BASE}/consulta-producao.aspx?tipo={t_id}&autor={aid}&ano={ano}")
                    if sub_csv:
                        lines = sub_csv.splitlines()
                        if not combined and lines:
                            combined.append(lines[0])
                        combined.extend(lines[1:])
                if combined:
                    with open(os.path.join(scratch_dir, "csv", f"autor_{aid}_{ano}.csv"), "w", encoding="utf-8") as out:
                        out.write("\n".join(combined))

        return {
            "pid": pid,
            "aid": aid,
            "ap": ap,
            "nome_civil": nome_civil or ap,
            "part": part,
            "tel": tel,
            "cel": cel,
            "email": email,
            "url": url,
            "mesa_raw": mesa_raw,
            "freq": freq,
            "bio": bio,
            "legislaturas": legislaturas,
            "comissoes": comissoes,
            "leis": leis_count,
            "emendas_impositivas": emendas_imp,
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        vereadores = list(ex.map(fetch_one_vereador, pids))

    with open(os.path.join(scratch_dir, "vereadores_raw.json"), "w", encoding="utf-8") as f:
        json.dump(vereadores, f, ensure_ascii=False, indent=2)

    # 2b. Coletar proposições de autoria do Prefeito Municipal (autor=20)
    pref_aid = autor_map.get("prefeito municipal", "20")
    for ano in years:
        u_pref = f"{SPL_BASE}/consulta-producao.aspx?autor={pref_aid}&ano={ano}"
        raw_pref = fetch_csv_from_spl(u_pref)
        if raw_pref:
            with open(os.path.join(scratch_dir, "csv", f"prefeito_{pref_aid}_{ano}.csv"), "w", encoding="utf-8") as out:
                out.write(raw_pref)

    # 3. Coletar sessões e PDFs de votação nominal
    url_ses = f"{SPL_BASE}/sessoes.aspx"
    h_ses = http_get(url_ses).decode("utf-8", errors="ignore")
    vs = re.search(r'id="__VIEWSTATE" value="([^"]*)"', h_ses).group(1)
    vsg = re.search(r'id="__VIEWSTATEGENERATOR" value="([^"]*)"', h_ses).group(1)
    ev = re.search(r'id="__EVENTVALIDATION" value="([^"]*)"', h_ses).group(1)
    data = urllib.parse.urlencode({
        "__VIEWSTATE": vs,
        "__VIEWSTATEGENERATOR": vsg,
        "__EVENTVALIDATION": ev,
        "ctl00$ContentPlaceHolder1$ddl_tipo_sessao": "",
        "ctl00$ContentPlaceHolder1$ddl_sessao_arquivo_tipo": "",
        "ctl00$ContentPlaceHolder1$txt_data_inicio": "2025-01-01",
        "ctl00$ContentPlaceHolder1$txt_data_final": f"{cur_year}-12-31",
        "ctl00$ContentPlaceHolder1$btn_buscar": "   FILTRAR   ",
    }).encode()
    page_html = urllib.request.urlopen(urllib.request.Request(url_ses, data=data, headers={"User-Agent": "Mozilla/5.0"}), timeout=30, context=SSL_CTX).read().decode("utf-8", errors="ignore")
    tot_pages = int(re.search(r'id="ContentPlaceHolder1_lvSessoes_TotalPages" value="(\d+)"', page_html).group(1))
    pages = [page_html]
    cur_html = page_html
    for p in range(1, tot_pages):
        vs = re.search(r'id="__VIEWSTATE" value="([^"]*)"', cur_html).group(1)
        vsg = re.search(r'id="__VIEWSTATEGENERATOR" value="([^"]*)"', cur_html).group(1)
        ev_m = re.search(r'id="__EVENTVALIDATION" value="([^"]*)"', cur_html)
        post_data = {
            "__EVENTTARGET": "ctl00$ContentPlaceHolder1$lvSessoes_lbNext",
            "__EVENTARGUMENT": "",
            "__VIEWSTATE": vs,
            "__VIEWSTATEGENERATOR": vsg,
            "ctl00$ContentPlaceHolder1$ddl_tipo_sessao": "",
            "ctl00$ContentPlaceHolder1$ddl_sessao_arquivo_tipo": "",
            "ctl00$ContentPlaceHolder1$txt_data_inicio": "2025-01-01",
            "ctl00$ContentPlaceHolder1$txt_data_final": f"{cur_year}-12-31",
            "ctl00$ContentPlaceHolder1$lvSessoes_TotalPages": str(tot_pages),
            "ctl00$ContentPlaceHolder1$lvSessoes_CurrentPage": str(p - 1),
        }
        if ev_m:
            post_data["__EVENTVALIDATION"] = ev_m.group(1)
        cur_html = urllib.request.urlopen(urllib.request.Request(url_ses, data=urllib.parse.urlencode(post_data).encode(), headers={"User-Agent": "Mozilla/5.0"}), timeout=30, context=SSL_CTX).read().decode("utf-8", errors="ignore")
        pages.append(cur_html)

    sessoes = []
    seen_ids = set()
    pdf_tasks = []
    for phtml in pages:
        for tr in re.findall(r"<tr>\s*<td>(.*?)</td>\s*</tr>", phtml, re.S):
            t_m = re.search(r"<strong>\s*(Ordinária|Extraordinária|Solene|Reunião de Comissão Permanente)\s*N°\s*(\d+)\s*</strong>", tr, re.S)
            if not t_m:
                continue
            tipo_s = " ".join(t_m.group(1).split())
            num_s = t_m.group(2)
            d_m = re.search(r"<strong>Data:\s*</strong>\s*(\d{2}/\d{2}/\d{4})", tr)
            dt_str = d_m.group(1) if d_m else ""
            pres_m = re.search(r"sessao-parlamentares\.aspx\?id=(\d+)", tr)
            ses_id_m = re.search(r"(?:sessao-parlamentares\.aspx\?id=|sessao-leitura\.aspx\?id=|/SES/)(\d+)", tr)
            ses_id = ses_id_m.group(1) if ses_id_m else f"{tipo_s}_{num_s}_{dt_str}"
            if ses_id in seen_ids:
                continue
            seen_ids.add(ses_id)
            vot_pdfs = re.findall(r"href=['\"](https://camarasempapel\.camarataubate\.sp\.gov\.br/Arquivo/Documents/SES/[^'\"]+)['\"][^>]*>Lista de Votações Nominais[^<]*</a>", tr)
            sessoes.append({
                "id": ses_id,
                "tipo": tipo_s,
                "num": num_s,
                "data": dt_str,
                "has_presenca": bool(pres_m),
                "vot_pdfs": vot_pdfs,
            })
            dt_iso = f"{dt_str[6:10]}-{dt_str[3:5]}-{dt_str[0:2]}"
            for purl in vot_pdfs:
                pdf_tasks.append((ses_id, dt_iso, purl))

    def fetch_and_parse_pdf(task):
        ses_id, dt_iso, purl = task
        raw_pdf = http_get(purl, timeout=30)
        return parse_pdf_votes(raw_pdf, ses_id, dt_iso, purl)

    all_votes = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        for parsed_list in ex.map(fetch_and_parse_pdf, pdf_tasks):
            all_votes.extend(parsed_list)

    with open(os.path.join(scratch_dir, "sessoes_raw.json"), "w", encoding="utf-8") as f:
        json.dump(sessoes, f, ensure_ascii=False, indent=2)
    with open(os.path.join(scratch_dir, "votacoes_parsed.json"), "w", encoding="utf-8") as f:
        json.dump(all_votes, f, ensure_ascii=False, indent=2)


def build_dados_js(scratch_dir: str, output_js_path: str):
    with open(os.path.join(scratch_dir, "vereadores_raw.json"), encoding="utf-8") as f:
        vereadores_raw = json.load(f)
    with open(os.path.join(scratch_dir, "sessoes_raw.json"), encoding="utf-8") as f:
        sessoes_raw = json.load(f)
    with open(os.path.join(scratch_dir, "votacoes_parsed.json"), encoding="utf-8") as f:
        votacoes_raw = json.load(f)

    # Ordenar vereadores alfabeticamente por apelido parlamentar
    vereadores_raw.sort(key=lambda x: norm(x["ap"]))

    # Mapear sessões com chamada registrada vs sem chamada registrada
    sess_list = []
    semreg_list = []
    for s in sessoes_raw:
        if s["tipo"] not in ("Ordinária", "Extraordinária", "Solene"):
            continue
        d_str = s["data"]
        dt_iso = f"{d_str[6:10]}-{d_str[3:5]}-{d_str[0:2]}"
        if s["has_presenca"]:
            sess_list.append({"d": dt_iso})
        else:
            semreg_list.append({"d": dt_iso, "n": f"{s['num']}ª Sessão {s['tipo']}"})

    sess_list.sort(key=lambda x: x["d"])
    semreg_list.sort(key=lambda x: x["d"], reverse=True)
    ult_sessao = sess_list[-1]["d"] if sess_list else "2026-11-10"

    # Índice de vereadores por nome normalizado para casar coautorias e votações
    ap_to_idx = {}
    for idx, v in enumerate(vereadores_raw):
        ap_to_idx[norm(v["ap"])] = idx
        ap_to_idx[norm(v.get("nome_civil", ""))] = idx

    # Ler todas as proposições dos CSVs e deduplicar por ID
    props_by_id = {}
    for path in sorted(glob.glob(os.path.join(scratch_dir, "csv", "autor_*.csv"))):
        fname = os.path.basename(path)
        m_f = re.match(r"autor_(\d+)_(\d{4})\.csv", fname)
        aid_file = m_f.group(1) if m_f else ""
        # Descobrir índice do vereador dono do arquivo
        owner_idx = None
        for idx, v in enumerate(vereadores_raw):
            if str(v.get("aid")) == aid_file:
                owner_idx = idx
                break

        with open(path, encoding="utf-8") as f:
            rows = parse_csv_content(f.read())
        for r in rows:
            if r["ano"] not in ("2025", "2026", "2027", "2028"):
                continue
            pid = r["id"]
            if pid not in props_by_id:
                props_by_id[pid] = {
                    "row": r,
                    "authors": set(),
                }
            if owner_idx is not None:
                props_by_id[pid]["authors"].add(owner_idx)
            for a_part in r["autor"].split(","):
                na = norm(a_part.strip())
                if na in ap_to_idx:
                    props_by_id[pid]["authors"].add(ap_to_idx[na])

    # Ler proposições do Prefeito Municipal (prefeito_*.csv)
    pref_props_by_id = {}
    for path in sorted(glob.glob(os.path.join(scratch_dir, "csv", "prefeito_*.csv"))):
        with open(path, encoding="utf-8") as f:
            rows = parse_csv_content(f.read())
        for r in rows:
            if r["ano"] not in ("2025", "2026", "2027", "2028"):
                continue
            pref_props_by_id[r["id"]] = r

    # Mapear resultados de votações nominais por título da proposição para enriquecer items e links de naos
    prop_code_to_id = {}
    for pid, r in pref_props_by_id.items():
        abbr = TIPO_ABBR.get(r["tipo"], r["tipo"][:3].upper())
        code = f"{abbr} {r['num']}/{r['ano']}"
        prop_code_to_id[code] = pid
        full_title = norm(f"{r['tipo']} nº {r['num']}/{r['ano']}")
        prop_code_to_id[full_title] = pid

    for pid, pinfo in props_by_id.items():
        r = pinfo["row"]
        abbr = TIPO_ABBR.get(r["tipo"], r["tipo"][:3].upper())
        code = f"{abbr} {r['num']}/{r['ano']}"
        prop_code_to_id[code] = pid
        # Também mapear nome completo para casar com PDF de votação
        full_title = norm(f"{r['tipo']} nº {r['num']}/{r['ano']}")
        prop_code_to_id[full_title] = pid

    vote_result_by_pid = {}
    for vt in votacoes_raw:
        ntitle = norm(vt["prop_title"])
        matched_pid = prop_code_to_id.get(ntitle)
        if not matched_pid:
            # Tentar extrair tipo + numero/ano
            m_t = re.search(r"(projeto de lei ordinaria|projeto de lei complementar|projeto de decreto legislativo|projeto de resolucao|mocao|requerimento|emenda|substitutivo)\s*n[ºo°]?\s*(\d+/\d{4})", ntitle)
            if m_t:
                key_t = f"{m_t.group(1)} nº {m_t.group(2)}"
                matched_pid = prop_code_to_id.get(key_t)
        if matched_pid and vt["resultado"]:
            res_str = "Aprovado" if "APROVAD" in vt["resultado"].upper() else ("Rejeitado" if "REJEITAD" in vt["resultado"].upper() else "")
            if res_str:
                vote_result_by_pid[matched_pid] = res_str
        vt["matched_pid"] = matched_pid

    # Construir lista de items e contagens por categoria, coautorias e cobranças pendentes
    catot = {"b": 0, "c": 0, "h": 0, "l": 0, "o": 0}
    v_cats = [{"b": 0, "c": 0, "h": 0, "l": 0, "o": 0} for _ in vereadores_raw]
    v_cob_pend = [0 for _ in vereadores_raw]
    coaut_counts = [Counter() for _ in vereadores_raw]
    cob_tot_all = 0
    cob_pend_all = 0
    cob_resp_all = 0

    # Ordenar proposições da mais recente para a mais antiga
    def sort_key(item_tuple):
        pid, pinfo = item_tuple
        d = pinfo["row"]["data"]
        aaaammdd = f"{d[6:10]}{d[3:5]}{d[0:2]}"
        return (aaaammdd, int(pid) if pid.isdigit() else 0)

    sorted_props = sorted(props_by_id.items(), key=sort_key, reverse=True)
    items = []
    for pid, pinfo in sorted_props:
        r = pinfo["row"]
        auts = sorted(pinfo["authors"])
        if not auts:
            continue
        abbr = TIPO_ABBR.get(r["tipo"], r["tipo"][:3].upper())
        code = f"{abbr} {r['num']}/{r['ano']}"
        d = r["data"]
        aaaammdd = f"{d[6:10]}{d[3:5]}{d[0:2]}"
        grupo, eh_materia, th = classify_item(r["tipo"], r["ementa"])

        # Resultado / status
        res_label = vote_result_by_pid.get(pid, "")
        if not res_label:
            if r["fase"] == "Retirar Proposição" or "retirad" in r["fase"].lower():
                res_label = "Pedido de Retirada"
            elif r["situacao"] == "Arquivado" and r["tipo"] in ("Moção", "Requerimento"):
                res_label = "Concluído"
            elif r["situacao"] == "Arquivado" and grupo == "l":
                res_label = "Concluído"

        # Código de situação para filtro: 'p' = aguardando Prefeitura, 't' = em tramitação, 'r' = retirado/rejeitado, 'a' = aprovado/concluído
        if res_label in ("Rejeitado", "Pedido de Retirada"):
            st_code = "r"
        elif r["situacao"] == "Tramitando" and ("prefeitura" in r["setor"].lower() or "prestar informações" in r["fase"].lower()):
            st_code = "p"
            if not res_label:
                res_label = "Aguardando Prefeitura"
        elif r["situacao"] == "Tramitando" and res_label != "Aprovado":
            st_code = "t"
        else:
            st_code = "a"

        if grupo == "c":
            cob_tot_all += 1
            if st_code == "p":
                cob_pend_all += 1
                for a_idx in auts:
                    v_cob_pend[a_idx] += 1
            elif st_code == "a":
                cob_resp_all += 1

        if len(auts) > 1:
            for i_a in auts:
                for j_a in auts:
                    if i_a != j_a:
                        coaut_counts[i_a][j_a] += 1

        items.append([
            pid,
            code,
            r["ementa"],
            aaaammdd,
            grupo,
            res_label,
            auts,
            eh_materia,
            th,
            st_code,
        ])
        catot[grupo] += 1
        for a_idx in auts:
            v_cats[a_idx][grupo] += 1

    # Processar proposições do Prefeito Municipal
    pref_items = []
    pref_plo = 0
    pref_plc = 0
    pref_ret = 0
    pref_aprov = 0
    pref_tram = 0
    pref_rej = 0

    sorted_pref = sorted(
        pref_props_by_id.items(),
        key=lambda kv: (f"{kv[1]['data'][6:10]}{kv[1]['data'][3:5]}{kv[1]['data'][0:2]}", int(kv[0]) if kv[0].isdigit() else 0),
        reverse=True,
    )
    for pid, r in sorted_pref:
        abbr = TIPO_ABBR.get(r["tipo"], "MSG" if "Mensagem" in r["tipo"] else r["tipo"][:3].upper())
        code = f"{abbr} {r['num']}/{r['ano']}"
        d = r["data"]
        aaaammdd = f"{d[6:10]}{d[3:5]}{d[0:2]}"
        if r["tipo"] == "Projeto de Lei Ordinária":
            pref_plo += 1
        elif r["tipo"] == "Projeto de Lei Complementar":
            pref_plc += 1
        elif "Mensagem" in r["tipo"] or "Retirada" in r["tipo"]:
            pref_ret += 1

        res_l = vote_result_by_pid.get(pid, "")
        if not res_l:
            if "retirad" in r["fase"].lower() or "Mensagem" in r["tipo"] or "Retirada" in r["tipo"]:
                res_l = "Retirada pelo Prefeito"
            elif r["situacao"] == "Arquivado":
                res_l = "Aprovado / Sancionado"
            else:
                res_l = "Em tramitação"

        if "Aprovado" in res_l:
            st_p = "a"
            pref_aprov += 1
        elif "Rejeitado" in res_l or "Retirad" in res_l:
            st_p = "r"
            pref_rej += 1
        else:
            st_p = "t"
            pref_tram += 1

        pref_items.append([
            pid,
            code,
            r["ementa"],
            aaaammdd,
            abbr,
            res_l,
            st_p,
        ])

    # Calcular votações nominais por vereador (vs, vn, va, naos), alinhamento com o Prefeito, vetos, rachas e matriz de concordância
    nvot = len(votacoes_raw)
    unan = 0
    v_votes = [{"vs": 0, "vn": 0, "va": 0, "naos": [], "alin_s": 0, "alin_t": 0} for _ in vereadores_raw]
    n_ver = len(vereadores_raw)
    vmat = [[[0, 0] for _ in range(n_ver)] for _ in range(n_ver)]
    rachas_list = []
    vetos_by_title = {}

    for vt in votacoes_raw:
        active_vals = [x for x in vt["votos"].values() if x in ("Sim", "Não", "Abstenção")]
        is_unan = bool(active_vals and len(set(active_vals)) == 1)
        if is_unan:
            unan += 1

        # Código curto da matéria votada
        short_t = vt["prop_title"]
        short_t = re.sub(r"Projeto de Lei Ordinária\s*n[º°]?\s*", "PL ", short_t, flags=re.I)
        short_t = re.sub(r"Projeto de Lei Complementar\s*n[º°]?\s*", "PLC ", short_t, flags=re.I)
        short_t = re.sub(r"Projeto de Decreto Legislativo\s*n[º°]?\s*", "PDL ", short_t, flags=re.I)
        short_t = re.sub(r"Projeto de Resolução\s*n[º°]?\s*", "PRE ", short_t, flags=re.I)
        short_t = re.sub(r"Proposta de Emenda à Lei Orgânica\s*n[º°]?\s*", "PEL ", short_t, flags=re.I)
        short_t = re.sub(r"Moç(?:ão|ões)\s*n[º°]?\s*", "MOC ", short_t, flags=re.I)
        short_t = re.sub(r"Requerimentos?\s*n[º°]?\s*", "REQ ", short_t, flags=re.I)

        link_u = f"{SPL_BASE}/processo.aspx?id={vt['matched_pid']}" if vt.get("matched_pid") else vt["url"]
        ementa_v = vt["ementa"] or f"{vt['prop_title']} ({vt['sess_name']} — {vt['turno']})"
        autoria_v = re.sub(r"^Vereador(?:a|es)?\s+", "", vt["autoria"] or "").strip()

        is_veto = "veto" in vt["prop_title"].lower()
        is_pref_bill = ("prefeito" in (vt["autoria"] or "").lower()) and not any(
            k in vt["prop_title"].lower() for k in ("emenda", "substitutivo", "subemenda")
        )
        is_pref_matter = is_veto or is_pref_bill

        sim_indices = []
        nao_indices = []
        abst_indices = []
        ver_vote_map = {}

        for pname, voto_str in vt["votos"].items():
            idx = ap_to_idx.get(norm(pname))
            if idx is None:
                continue
            if voto_str in ("Sim", "Não", "Abstenção"):
                ver_vote_map[idx] = voto_str
                if is_pref_matter:
                    v_votes[idx]["alin_t"] += 1
                    if voto_str == "Sim":
                        v_votes[idx]["alin_s"] += 1

            if voto_str == "Sim":
                v_votes[idx]["vs"] += 1
                sim_indices.append(idx)
            elif voto_str == "Não":
                v_votes[idx]["vn"] += 1
                nao_indices.append(idx)
                v_votes[idx]["naos"].append({
                    "t": short_t,
                    "d": vt["data"],
                    "e": ementa_v[:280],
                    "u": link_u,
                    "v": "nao",
                    "a": autoria_v,
                })
            elif voto_str == "Abstenção":
                v_votes[idx]["va"] += 1
                abst_indices.append(idx)
                v_votes[idx]["naos"].append({
                    "t": short_t,
                    "d": vt["data"],
                    "e": ementa_v[:280],
                    "u": link_u,
                    "v": "abst",
                    "a": autoria_v,
                })

        sim_indices.sort()
        nao_indices.sort()
        abst_indices.sort()

        # Atualizar matriz de concordância par-a-par
        voted_idxs = list(ver_vote_map.keys())
        for i1 in range(len(voted_idxs)):
            u1 = voted_idxs[i1]
            v1 = ver_vote_map[u1]
            for i2 in range(i1, len(voted_idxs)):
                u2 = voted_idxs[i2]
                v2 = ver_vote_map[u2]
                vmat[u1][u2][1] += 1
                if u1 != u2:
                    vmat[u2][u1][1] += 1
                if v1 == v2:
                    vmat[u1][u2][0] += 1
                    if u1 != u2:
                        vmat[u2][u1][0] += 1

        # Se for veto do Prefeito, guardar placar consolidado
        if is_veto:
            res_up = (vt["resultado"] or "").upper()
            if "MANTID" in res_up or "APROVAD" in res_up:
                v_status = "Mantido"
            elif "DERRUBAD" in res_up or "REJEITAD" in res_up:
                v_status = "Derrubado"
            else:
                v_status = vt["resultado"] or "Votado"
            clean_vt_t = re.sub(r"^Discussão e votação única do\s+", "", short_t, flags=re.I).strip()
            if clean_vt_t.endswith("PL"):
                m_pl = re.search(r"(\d+/\d{4})", ementa_v)
                if m_pl:
                    clean_vt_t = f"{clean_vt_t} {m_pl.group(1)}"
            vetos_by_title[vt["prop_title"]] = {
                "t": clean_vt_t,
                "d": vt["data"],
                "e": ementa_v[:280],
                "aut": autoria_v or "Câmara Municipal",
                "status": v_status,
                "s": len(sim_indices),
                "n": len(nao_indices),
                "a": len(abst_indices),
                "u": link_u,
                "vs": sim_indices,
                "vn": nao_indices,
                "va": abst_indices,
            }

        # Se não foi unânime (teve voto Não ou Abstenção), incluir em rachas
        if not is_unan and (nao_indices or abst_indices):
            res_up = (vt["resultado"] or "").upper()
            if is_veto:
                res_clean = "Veto Mantido" if ("MANTID" in res_up or "APROVAD" in res_up) else ("Veto Derrubado" if ("DERRUBAD" in res_up or "REJEITAD" in res_up) else (vt["resultado"] or ""))
            else:
                res_clean = "Aprovado" if "APROVAD" in res_up else ("Rejeitado" if "REJEITAD" in res_up else (vt["resultado"] or ""))
            rachas_list.append({
                "t": short_t,
                "d": vt["data"],
                "turno": vt.get("turno", ""),
                "e": ementa_v[:280],
                "aut": autoria_v or "Prefeito Municipal",
                "res": res_clean,
                "u": link_u,
                "s": sim_indices,
                "n": nao_indices,
                "a": abst_indices,
                "pref": 1 if is_pref_matter else 0,
            })

    # Ordenar rachas por grau de divisão (menor lado maior primeiro, depois mais recente)
    rachas_list.sort(key=lambda x: (min(len(x["s"]), len(x["n"]) + len(x["a"])), len(x["n"]) + len(x["a"]), x["d"]), reverse=True)

    vetos_list = sorted(vetos_by_title.values(), key=lambda x: x["d"], reverse=True)
    vetos_mant = sum(1 for x in vetos_list if x["status"] == "Mantido")
    vetos_derr = sum(1 for x in vetos_list if x["status"] == "Derrubado")

    # Construir lista V de vereadores no formato exato de window.RX.v
    v_out = []
    for idx, v in enumerate(vereadores_raw):
        pid = str(v["pid"])
        freq = v.get("freq", {})
        def sum_f(k):
            return sum(int(val) for val in freq.get(k, {}).values() if str(val).isdigit())

        P = sum_f("Presente")
        A = sum_f("Falta Justificada") + sum_f("Licenciado") + sum_f("Afastado")
        F = sum_f("Falta")

        # Cargo na Mesa Diretora
        mesa = ""
        mr = v.get("mesa_raw", "")
        if "Presidente" in mr or "Secretári" in mr:
            m_cargo = re.search(r"(Presidente|1º Vice-Presidente|2º Vice-Presidente|1º Secretário|2º Secretário|1ª Secretária|2ª Secretária)", mr)
            if m_cargo:
                mesa = m_cargo.group(1)

        # Votos em 2024
        votos_matches = re.findall(r"(\d[\d\.]*)\s*votos", v.get("bio", ""), re.I)
        if votos_matches:
            votos_2024 = int(votos_matches[-1].replace(".", ""))
        else:
            votos_2024 = VOTOS_2024_FALLBACK.get(pid, 0)

        # Telefone principal do gabinete
        tel_raw = v.get("tel", "").split("/")[0].strip()

        # Ordenar naos por data decrescente
        naos_sorted = sorted(v_votes[idx]["naos"], key=lambda x: x["d"], reverse=True)

        # Histórico de mandatos / tempo como vereador
        legs_raw = v.get("legislaturas", [])
        seen_leg_names = []
        mand_periods = []
        years_ini = []
        for lg in legs_raw:
            lname = lg.get("leg", "")
            if lname and lname not in seen_leg_names:
                seen_leg_names.append(lname)
                y0 = lg.get("ini", "")[-4:]
                y1 = lg.get("fim", "")[-4:]
                if y0.isdigit():
                    years_ini.append(int(y0))
                if y0 and y1:
                    mand_periods.append(f"{y0}–{y1}")

        # Caso especial documentado na biografia oficial: Bilili de Angelis (pid=2)
        # foi eleito para a 11ª Legislatura (1993-1996), 16ª (2013-2016), 17ª (2017-2020) e 19ª (2025-2028)
        # (em 2021-2024 exerceu suplência temporária).
        if pid == "2":
            mand_count = 4
            desde_ano = 1993
            mand_hist = ["1993–1996", "2013–2016", "2017–2020", "2025–2028"]
            mand_txt = "4º mandato · 1ª vez em 1993"
        else:
            mand_count = len(seen_leg_names) if seen_leg_names else 1
            desde_ano = min(years_ini) if years_ini else 2025
            mand_hist = list(reversed(mand_periods)) if mand_periods else ["2025–2028"]
            mand_txt = f"{mand_count}º mandato · desde {desde_ano}"

        nota_exec = ""
        if pid == "42":
            nota_exec = "Vice-prefeito (2013–2020)"
        elif pid == "27":
            nota_exec = "Suplente em 2016"

        # Leis sancionadas / promulgadas
        leis_dict = v.get("leis", {})
        leis_tot = sum(leis_dict.values())
        leis_ord = (
            leis_dict.get("Lei Ordinária", 0)
            + leis_dict.get("Lei Complementar", 0)
            + leis_dict.get("Emenda à Lei Orgânica", 0)
        )

        # Comissões permanentes atuais
        coms_out = [
            {"c": c.get("cargo", ""), "n": re.sub(r"^Comissão\s+(?:Permanente\s+|Especial\s+)?de\s+", "", c.get("nome", ""))}
            for c in v.get("comissoes", [])
        ]

        # Emendas impositivas
        em_imp_out = [
            {"a": e.get("ano", ""), "u": e.get("url", "")}
            for e in v.get("emendas_impositivas", [])
            if e.get("ano") in ("2026", "2025", "2024")
        ]

        # Alinhamento com o Prefeito
        alin_s = v_votes[idx]["alin_s"]
        alin_t = v_votes[idx]["alin_t"]
        alin_pct = round(100 * alin_s / alin_t) if alin_t > 0 else 0

        # Principais parceiros de coautoria
        top_parc = [[other_i, cnt] for other_i, cnt in coaut_counts[idx].most_common(3)]

        # Prestação de contas e histórico eleitoral (TSE)
        tse_info = TSE_POR_PID.get(pid, {})
        gasto24 = tse_info.get("gasto24", 0.0)
        rec24 = tse_info.get("rec24", 0.0)
        gasto20 = tse_info.get("gasto20", 0.0)
        cpv24 = round(gasto24 / votos_2024, 2) if votos_2024 > 0 else 0.0
        outras_cand = tse_info.get("outras", [])
        hist_tse = tse_info.get("hist", [])

        v_out.append({
            "id": pid,
            "nome": v.get("nome_civil") or v["ap"],
            "ap": v["ap"],
            "part": v["part"],
            "votos": votos_2024,
            "ini": "2025-01-01",
            "mesa": mesa,
            "P": P,
            "A": A,
            "F": F,
            "email": v.get("email", ""),
            "tel": tel_raw,
            "whats": "",
            "vs": v_votes[idx]["vs"],
            "vn": v_votes[idx]["vn"],
            "va": v_votes[idx]["va"],
            "naos": naos_sorted,
            "cat": v_cats[idx],
            "url": f"{SPL_BASE}/parlamentar.aspx?id={pid}",
            "foto": 1,
            "mand": mand_count,
            "desde": desde_ano,
            "mand_txt": mand_txt,
            "mand_hist": mand_hist,
            "nota_exec": nota_exec,
            "leis_tot": leis_tot,
            "leis_ord": leis_ord,
            "leis_det": leis_dict,
            "coms": coms_out,
            "em_imp": em_imp_out,
            "alin": alin_pct,
            "alin_s": alin_s,
            "alin_t": alin_t,
            "parc": top_parc,
            "cob_pend": v_cob_pend[idx],
            "rec24": rec24,
            "gasto24": gasto24,
            "cpv24": cpv24,
            "gasto20": gasto20,
            "outras_cand": outras_cand,
            "hist_tse": hist_tse,
        })

    # Calcular contagem por bairro de Taubaté (compatível 100% com a busca runQ do portal)
    norm_items_text = [norm(it[2] + " " + it[1]) for it in items]
    bairros_pairs = []
    for b in BAIRROS_TAUBATE:
        nb = norm(b)
        cnt = sum(1 for txt in norm_items_text if nb in txt)
        if cnt > 0:
            bairros_pairs.append((b, cnt))
    bairros_pairs.sort(key=lambda x: -x[1])
    bairros_out = [b for b, _ in bairros_pairs]
    bairrosn_out = [c for _, c in bairros_pairs]

    # Calcular problemas repetidos na mesma rua + mesmo tema (rep)
    rep_groups = defaultdict(list)
    for item_idx, it in enumerate(items):
        pid, code, txt, aaaammdd, grp, res_l, auts, ehm, th = it[:9]
        if grp not in ("b", "c") or not th:
            continue
        m_st = STREET_PAT.search(txt)
        if not m_st:
            continue
        st = re.sub(r"\s+", " ", m_st.group(1)).strip(" .,;-–")
        st = re.sub(r"^(?i:av\.|avenida)\s+", "Avenida ", st)
        st = re.sub(r"^(?i:rua)\s+", "Rua ", st)
        st = re.sub(r"^(?i:praça)\s+", "Praça ", st)
        st = re.sub(r"^(?i:estrada)\s+", "Estrada ", st)
        if len(st.split()) < 2 or len(st) > 65:
            continue
        nst = (
            norm(st)
            .replace("teresinha", "terezinha")
            .replace("doutor ", "dr. ")
            .replace("comendador ", "com. ")
            .replace("professor ", "prof. ")
            .replace("professora ", "profa. ")
        )
        rep_groups[(nst, th)].append((st, item_idx, aaaammdd, auts, txt))

    rep_out = []
    for (nst, th), lst in rep_groups.items():
        if len(lst) < 3:
            continue
        st_name = Counter(x[0] for x in lst).most_common(1)[0][0]
        # Identificar bairro mencionado nos pedidos dessa rua
        found_b = ""
        for _, _, _, _, txt in lst:
            ntxt = norm(txt)
            for b in bairros_out:
                if norm(b) in ntxt:
                    found_b = b
                    break
            if found_b:
                break
        all_auts = set()
        for _, _, _, auts, _ in lst:
            all_auts.update(auts)
        dates = sorted(x[2] for x in lst)
        ids = sorted(x[1] for x in lst)
        rep_out.append({
            "r": st_name,
            "b": found_b,
            "th": th,
            "n": len(lst),
            "a": len(all_auts),
            "d0": dates[0],
            "d1": dates[-1],
            "ids": ids,
        })

    rep_out.sort(key=lambda x: (-x["n"], -x["a"], x["r"]))

    # Validação de segurança (Passo 6 do Guia)
    if len(v_out) != 19:
        raise RuntimeError(f"Validação falhou: esperado 19 vereadores, obtido {len(v_out)}")
    if len(sess_list) < 90:
        raise RuntimeError(f"Validação falhou: poucas sessões coletadas ({len(sess_list)})")
    if len(items) < 5000:
        raise RuntimeError(f"Validação falhou: poucas proposições coletadas ({len(items)})")
    if nvot < 500:
        raise RuntimeError(f"Validação falhou: poucas votações nominais coletadas ({nvot})")

    now_br = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-3)))
    rx = {
        "ger": now_br.strftime("%Y-%m-%d"),
        "gerh": now_br.strftime("%Y-%m-%dT%H:%M-03:00"),
        "posse": "2025-01-01",
        "rep": rep_out,
        "ult": ult_sessao,
        "sess": sess_list,
        "semreg": semreg_list,
        "nvot": nvot,
        "unan": unan,
        "v": v_out,
        "items": items,
        "catot": catot,
        "bairros": bairros_out,
        "bairrosn": bairrosn_out,
        "sal": {
            "v": 12000,
            "lei": "Decreto Legislativo nº 639/2021",
            "u": f"{SPL_BASE}/processo.aspx?id=51292",
        },
        "pref": {
            "nome": "Sérgio Victor",
            "civil": "Sérgio Victor Oliveira",
            "part": "NOVO",
            "vice": "Coronel Oliveira Neto",
            "votos_1t": 61931,
            "votos_2t": 97450,
            "pct_2t": "64,07%",
            "posse": "2025-01-01",
            "sal": 24487,
            "tot": len(pref_items),
            "plo": pref_plo,
            "plc": pref_plc,
            "ret": pref_ret,
            "aprov": pref_aprov,
            "tram": pref_tram,
            "rej": pref_rej,
            "items": pref_items,
            "vetos_tot": len(vetos_list),
            "vetos_mant": vetos_mant,
            "vetos_derr": vetos_derr,
            "vetos": vetos_list,
            "cob_tot": cob_tot_all,
            "cob_pend": cob_pend_all,
            "cob_resp": cob_resp_all,
            "rec24": TSE_PREFEITO["rec24"],
            "gasto24": TSE_PREFEITO["gasto24"],
            "cpv24": TSE_PREFEITO["cpv24"],
            "outras_cand": TSE_PREFEITO["outras"],
            "hist_tse": TSE_PREFEITO["hist"],
        },
        "rachas": rachas_list,
        "vmat": vmat,
    }

    js_content = "window.RX=" + json.dumps(rx, ensure_ascii=False, separators=(",", ":")) + ";\n"
    with open(output_js_path, "w", encoding="utf-8") as f:
        f.write(js_content)

    print(
        f"Sucesso! dados.js gerado ({len(js_content)//1024} KB): "
        f"{len(v_out)} vereadores, {len(sess_list)} sessões (+{len(semreg_list)} sem chamada), "
        f"{len(items)} proposições, {nvot} votações nominais ({unan} unânimes), "
        f"{len(rep_out)} ruas com problemas repetidos."
    )


if __name__ == "__main__":
    out_path = os.path.join(ROOT_DIR, "dados.js")
    if "--local-cache" in sys.argv:
        idx = sys.argv.index("--local-cache")
        cache_dir = sys.argv[idx + 1]
        build_dados_js(cache_dir, out_path)
    else:
        tmp_dir = os.path.join(ROOT_DIR, ".cache_coleta")
        collect_live(tmp_dir)
        build_dados_js(tmp_dir, out_path)
