# HQ Reader

HQ Reader é um leitor pessoal de quadrinhos (CBZ, CBR e PDF) que roda como um site próprio, pensado para ler HQs e mangás direto do navegador, sem depender de aplicativos de terceiros.

## Como o projeto nasceu

Esse projeto nasceu de um problema simples: eu tinha um iPad antigo, sem suporte às versões mais novas de apps de leitura de quadrinhos, e queria usar esse aparelho só para ler HQs. Em vez de depender de um app específico (que provavelmente não seria mais atualizado para aquele iOS), resolvi construir um site que qualquer navegador consegue abrir, incluindo o Safari antigo daquele aparelho.

A ideia central é simples: o servidor guarda a biblioteca de HQs, faz a extração das páginas sob demanda e entrega só imagens simples para o navegador. O iPad não precisa processar nada pesado, só rolar e trocar de página.

## Por que funciona bem em um iPad antigo

Alguns pontos do projeto foram pensados especificamente para isso:

- O site é um PWA (Progressive Web App). Dá para "Adicionar à Tela de Início" e ele abre em tela cheia, sem barra de navegador, parecendo um app nativo, mesmo em iOS antigo que não roda apps modernos da App Store.
- A extração de páginas (dos arquivos CBZ/CBR) acontece no servidor, não no aparelho. O iPad nunca precisa descompactar um arquivo grande nem guardar o volume inteiro em disco, ele só recebe uma imagem JPEG/PNG por vez.
- As páginas já extraídas ficam em cache no servidor, então reabrir uma HQ ou avançar página é praticamente instantâneo, sem reprocessar o arquivo de novo.
- A interface é enxuta, com tema escuro, navegação por toque e paginação simples (anterior/próxima), sem elementos pesados de JavaScript que pesariam em hardware antigo.
- Por rodar via navegador, funciona em qualquer aparelho na mesma rede (iPad, celular, tablet Android, notebook), não só no aparelho que originou o projeto.

## De onde vêm os links das HQs

O painel administrativo tem uma opção de adicionar HQs a partir de um link de postagem do site [soquadrinhos.com](https://site.soquadrinhos.com/). O sistema lê a página informada, encontra os links de download (Mega ou MediaFire) publicados naquele post e baixa os arquivos automaticamente para a pasta correta da biblioteca, organizados por editora e série.

Também é possível adicionar HQs manualmente pelo painel, fazendo upload direto de um arquivo CBZ, CBR ou PDF.

## Este é um projeto de acervo pessoal

Este projeto foi criado para uso pessoal, como um leitor e organizador da minha própria coleção de quadrinhos. Ele não hospeda, distribui nem redistribui nenhum conteúdo publicamente: cada instância roda de forma privada, protegida por login, e os arquivos usados nela são de responsabilidade de quem os adiciona.

Os quadrinhos e mangás continuam sendo propriedade de seus respectivos autores e editoras. Este repositório contém apenas o código do site, não o conteúdo das HQs.

## Funcionalidades

- Biblioteca organizada por editora e série, com busca por título.
- Leitor de páginas para CBZ/CBR, com extração e cache automáticos.
- Leitor de PDF nativo do navegador.
- Continuar leitura de onde parou.
- Painel administrativo com upload manual e importação automática via link do soquadrinhos.com.
- Fila de downloads em segundo plano (worker separado), com acompanhamento de progresso.
- Dois níveis de acesso: administrador (gerencia a biblioteca) e leitor (só acessa a leitura).
- Instalável como PWA, com ícone e modo tela cheia.

## Stack técnica

- Backend: Python (Flask), gunicorn como servidor de produção.
- Extração de arquivos: zipfile (CBZ) e unrar (CBR).
- Fila de downloads: worker próprio (feeder_worker.py) consultando um banco SQLite.
- Frontend: HTML, CSS e JavaScript puro (sem framework), com manifest para instalação como PWA.
- Deploy: Docker e docker-compose, com nginx como proxy reverso.

## Rodando localmente (Windows)

Pré-requisitos: Python 3.12+ e, para arquivos CBR, o UnRAR instalado.

```
start.bat
```

O script cria o ambiente virtual, instala as dependências e sobe o servidor em `http://localhost:5000`. Para acessar de outro aparelho na mesma rede Wi-Fi (como um iPad), use o IP local do computador em vez de `localhost`.

## Rodando com Docker

```
docker-compose up -d
```

Isso sobe três serviços: o site (`web`), o worker de downloads (`feeder`) e um proxy `nginx` na porta 8090.

Antes de subir, copie `.env.example` para `.env` e preencha as variáveis de ambiente (usuário e senha de administrador, usuário e senha de leitura, chave secreta da sessão).

## Estrutura de pastas

```
app.py              rotas do site e do painel administrativo
comics_lib.py        configuração de diretórios e helpers de caminho
feeder.py             busca e download de links (Mega/MediaFire)
feeder_worker.py    worker que processa a fila de downloads em segundo plano
jobs_db.py            persistência da fila de downloads (SQLite)
templates/            páginas HTML (biblioteca, série, leitor, admin, login)
static/                  CSS, JavaScript e ícones do PWA
comics/                 biblioteca de HQs (pasta versionada vazia; conteúdo não é versionado)
cache/                   páginas extraídas e banco de jobs (pasta versionada vazia; conteúdo não é versionado)
```

## Aviso

Este é um projeto pessoal e educacional. Use-o apenas para organizar e ler conteúdo que você já possui o direito de acessar. Respeite os direitos autorais dos criadores e editoras dos quadrinhos e mangás.
