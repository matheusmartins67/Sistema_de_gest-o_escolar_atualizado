# Sistema de Gestão Escolar

Aplicação Flask para cursos, professores, turmas, alunos, matrículas e notas.

## API da Biblioteca Escolar

As rotas abaixo retornam JSON e não exigem login:

| Método | Rota | Uso |
| --- | --- | --- |
| `GET` | `/api/biblioteca` | Exibe a mensagem inicial e os caminhos disponíveis. |
| `GET` | `/api/biblioteca/livros` | Lista os títulos disponíveis no catálogo. |
| `GET` | `/api/biblioteca/livros/<livro_id>` | Consulta um livro pelo identificador, por exemplo `/api/biblioteca/livros/1`. |
| `POST` | `/api/biblioteca/livros` | Planeja o cadastro de um livro, recebendo JSON com `titulo` e `autor`. Ainda não grava no catálogo. |

A página `/biblioteca` abre um alerta de boas-vindas no navegador e possui um link para a lista de livros.

Exemplo de planejamento de cadastro:

```json
{
  "titulo": "A Bolsa Amarela",
  "autor": "Lygia Bojunga"
}
```

## Iniciar o servidor

### Windows

1. Extraia o projeto.
2. Dê duplo clique em `INICIAR_SERVIDOR.bat`.
3. Abra `http://localhost:5000`.

### Terminal

```bash
python -m venv .venv
```

No Windows:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

No macOS/Linux:

```bash
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Para parar, pressione `Ctrl+C` na janela do servidor.

## Primeiro acesso

Em um banco novo, o administrador é criado automaticamente:

| E-mail | Senha |
| --- | --- |
| `admin@escola.com` | `Mudar@123` |

Antes de publicar, defina `INITIAL_ADMIN_EMAIL`, `INITIAL_ADMIN_PASSWORD` e
`SECRET_KEY` no ambiente.

## Ordem de uso

1. Crie o **Curso** e informe as matérias.
2. Cadastre os **Professores**.
3. Cadastre os **Alunos**.
4. Crie as **Turmas**, escolhendo curso e professor.
5. Em **Turmas**, use **Gerenciar alunos** para fazer as matrículas.
6. Em **Notas**, lance três notas; a média é calculada automaticamente.

## Assistente Escolar

Depois do login, acesse **Assistente** no menu para tirar dúvidas sobre o uso
do sistema. O assistente orienta os fluxos de cadastro, turmas, matrículas,
notas e frequência sem realizar alterações automaticamente.

- Alunos podem consultar as próprias turmas, notas, frequência e parcelas.
- Professores podem consultar as próprias turmas e receber orientações para
  registrar notas e frequência.
- As respostas respeitam o perfil autenticado; o assistente não consulta dados
  de outros alunos nem solicita senhas ou documentos sensíveis.

### Ativar a IA generativa pela API

O assistente já funciona no modo local, com orientações e consultas autorizadas
ao banco. Para ativar respostas generativas da OpenAI, crie um arquivo `.env`
na raiz do projeto (copie o `.env.example`) e informe sua chave:

```env
OPENAI_API_KEY=sua_chave_da_openai
OPENAI_MODEL=gpt-4.1-mini
```

Reinicie o servidor depois de salvar. A chave fica apenas no seu computador e
não deve ser enviada ao GitHub. Quando a API estiver conectada, o chat mostra
“IA conectada”; sem chave ou em caso de indisponibilidade, ele usa
automaticamente a assistência local sem interromper o sistema.

## Dados locais

- Banco: `data/escola.db`.
- Uploads: `data/uploads`.
- Esses arquivos não devem ser enviados ao GitHub.

## Testes

```bash
python -m unittest discover tests -v
```

## Docker

Copie `.env.example` para `.env`, defina `SECRET_KEY` e execute:

```bash
docker compose up --build
```

## Subir para o GitHub

O projeto inclui `.gitignore`, `requirements.txt`, `.env.example`, Docker e
teste automático em `.github/workflows/tests.yml`.

```bash
git init
git add .
git commit -m "Sistema de gestão escolar"
git branch -M main
git remote add origin https://github.com/SEU-USUARIO/SEU-REPOSITORIO.git
git push -u origin main
```

Não envie `.env`, `data/`, bancos `.db`, uploads ou senhas.
