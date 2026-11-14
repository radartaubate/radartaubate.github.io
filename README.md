# Radar Taubaté (`radartaubate`)

Raio-X independente e automatizado da **Câmara Municipal de Taubaté/SP** (19ª Legislatura — 2025–2028), construído nos moldes exatos do projeto [Radar PTlândia](https://radarptlandia.org/) (de Gabriel Damasceno).

## O que o portal mostra

1. **Contador de salários em tempo real**: Estimativa proporcional desde a posse (1º de janeiro de 2025) para os 19 vereadores, com base no [Decreto Legislativo nº 639/2021](https://camarasempapel.camarataubate.sp.gov.br/spl/processo.aspx?id=51292) (R$ 12.000/mês brutos).
2. **O que pediram pelo seu bairro?**: Busca instantânea por bairro ou rua de Taubaté (Barreiro, Gurilândia, Quiririm, São Gonçalo, Estiva, Independência, Cecap, etc.) com ranking dos vereadores que mais pediram, principais temas e lista completa de proposições com link direto para o processo oficial na Câmara.
3. **O problema que não some**: Cruzamento automático das ruas e praças de Taubaté que receberam múltiplos pedidos para o mesmo problema em diferentes datas, com gerador de mensagem de cobrança pronta para enviar por e-mail oficial do gabinete ou WhatsApp do bairro.
4. **Homenagem ou trabalho?**: Divisão de todas as proposições em 5 grupos com código de cores fixo:
   - **Pedidos de melhoria nos bairros** (`azul`)
   - **Perguntas e cobranças** (`laranja`)
   - **Homenagens** (`rosa`)
   - **Propostas de lei** (`verde`)
   - **Outros** (`cinza`)
5. **Os 19 vereadores (Crachás)**: Presença oficial em plenário, ausências justificadas, faltas, salário mensal, votos recebidos em 2024, produção legislativa por categoria e histórico em votações nominais (incluindo todas as vezes em que cada vereador votou **"Não"** ou **"Abstenção"**).

## Estrutura de arquivos

- `index.html`: Aplicação completa (HTML + CSS + JS) sem dependências externas.
- `dados.js`: Base consolidada (`window.RX`) gerada automaticamente a partir do sistema legislativo oficial da Câmara (`camarasempapel.camarataubate.sp.gov.br`).
- `fotos/{id}.jpg`: Fotos oficiais dos 19 vereadores.
- `coletar.py`: Robô em Python 3 puro (zero dependências externas) que coleta os dados da Câmara, cruza sessões, extrai PDFs de votações nominais e valida a integridade antes de atualizar `dados.js`.
- `.github/workflows/atualizar.yml`: Automação diária do GitHub Actions (roda toda madrugada às 04h15 BRT e também sob demanda pelo botão *Run workflow*).

## Como testar localmente

Abra um servidor HTTP simples na pasta do projeto:

```bash
cd radar-taubate
python3 -m http.server 8080
```

E acesse `http://localhost:8080` no navegador.

## Como publicar de graça no GitHub Pages

1. Crie um repositório público no GitHub (por exemplo, `radar-taubate`).
2. Envie os arquivos desta pasta:
   ```bash
   git init
   git add .
   git commit -m "feat: portal Radar Taubaté"
   git branch -M main
   git remote add origin https://github.com/radartaubate/radar-taubate.git
   git push -u origin main
   ```
3. No GitHub, vá em **Settings → Pages** e em **Source** selecione `Deploy from a branch` → branch `main` / `/ (root)`.
4. Na aba **Actions**, habilite os workflows para que o robô `Atualizar dados do Radar Taubaté` rode automaticamente toda madrugada.
