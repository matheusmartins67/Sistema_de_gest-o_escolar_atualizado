"""Assistente contextual do Sistema de Gestão Escolar.

O módulo não executa alterações: ele orienta e consulta somente informações
que pertencem ao usuário logado ou às turmas do professor logado.
"""

from __future__ import annotations

import os
import re
import unicodedata

import requests


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFD", texto.lower())
    texto = "".join(char for char in texto if unicodedata.category(char) != "Mn")
    return " ".join(texto.split())


def _formatar_lista(itens: list[str], vazio: str) -> str:
    return "\n".join(f"• {item}" for item in itens) if itens else vazio


def _turmas_do_aluno(query, aluno_id: int) -> str:
    linhas = query(
        '''SELECT t.nome, t.codigo, c.nome AS curso, p.nome AS professor
           FROM matriculas m
           JOIN turmas t ON t.id = m.turma_id
           JOIN cursos c ON c.id = t.curso_id
           JOIN professores p ON p.id = t.professor_id
           WHERE m.aluno_id = ? AND m.status = 'ativa'
           ORDER BY t.nome''',
        (aluno_id,),
    ) or []
    return _formatar_lista(
        [f"{item['nome']} ({item['codigo']}) — {item['curso']}; professor(a): {item['professor']}" for item in linhas],
        "Você não possui turmas ativas vinculadas no momento.",
    )


def _notas_do_aluno(query, aluno_id: int) -> str:
    linhas = query(
        '''SELECT mo.nome AS modulo, t.nome AS turma, n.primeira_nota, n.segunda_nota,
                  n.terceira_nota, n.media_final
           FROM notas n
           JOIN matriculas mat ON mat.id = n.matricula_id
           JOIN modulos mo ON mo.id = n.modulo_id
           JOIN turmas t ON t.id = mat.turma_id
           WHERE mat.aluno_id = ? ORDER BY t.nome, mo.ordem, mo.nome''',
        (aluno_id,),
    ) or []
    return _formatar_lista(
        [f"{item['turma']} — {item['modulo']}: notas {item['primeira_nota']}, {item['segunda_nota']}, {item['terceira_nota']} | média {item['media_final']}" for item in linhas],
        "Ainda não há notas lançadas para você.",
    )


def _frequencia_do_aluno(query, aluno_id: int) -> str:
    linhas = query(
        '''SELECT t.nome AS turma, COUNT(f.id) AS aulas,
                  COALESCE(SUM(CASE WHEN f.presente = 1 THEN 1 ELSE 0 END), 0) AS presencas
           FROM matriculas m
           JOIN turmas t ON t.id = m.turma_id
           LEFT JOIN frequencias f ON f.matricula_id = m.id
           WHERE m.aluno_id = ? AND m.status = 'ativa'
           GROUP BY m.id, t.nome ORDER BY t.nome''',
        (aluno_id,),
    ) or []
    itens = []
    for item in linhas:
        aulas = item['aulas']
        if not aulas:
            itens.append(f"{item['turma']}: ainda não há frequência registrada.")
        else:
            percentual = item['presencas'] * 100 / aulas
            itens.append(f"{item['turma']}: {item['presencas']} presença(s) em {aulas} aula(s) ({percentual:.1f}%).")
    return _formatar_lista(itens, "Você não possui turmas ativas vinculadas no momento.")


def _financeiro_do_aluno(query, aluno_id: int) -> str:
    linhas = query(
        '''SELECT p.numero_parcela, p.valor_parcela, p.data_vencimento, p.status
           FROM parcelas p
           JOIN financeiro f ON f.id = p.financeiro_id
           JOIN matriculas m ON m.id = f.matricula_id
           WHERE m.aluno_id = ? ORDER BY p.data_vencimento, p.numero_parcela''',
        (aluno_id,),
    ) or []
    return _formatar_lista(
        [f"Parcela {item['numero_parcela']}: R$ {float(item['valor_parcela'] or 0):.2f} — vencimento {item['data_vencimento'] or 'não informado'} — {item['status']}." for item in linhas],
        "Não encontrei parcelas vinculadas ao seu cadastro.",
    )


def _turmas_do_professor(query, professor_id: int) -> str:
    linhas = query(
        '''SELECT t.nome, t.codigo, c.nome AS curso, COUNT(m.id) AS total_alunos
           FROM turmas t
           JOIN cursos c ON c.id = t.curso_id
           LEFT JOIN matriculas m ON m.turma_id = t.id AND m.status = 'ativa'
           WHERE t.professor_id = ? AND t.ativa = 1
           GROUP BY t.id ORDER BY t.nome''',
        (professor_id,),
    ) or []
    return _formatar_lista(
        [f"{item['nome']} ({item['codigo']}) — {item['curso']} — {item['total_alunos']} aluno(s) ativo(s)." for item in linhas],
        "Você não possui turmas ativas vinculadas no momento.",
    )


def _media_de_texto(texto: str) -> str | None:
    valores = re.findall(r"(?<!\w)\d+(?:[,.]\d+)?", texto)
    if len(valores) < 3:
        return None
    try:
        notas = [float(valor.replace(',', '.')) for valor in valores[:3]]
    except ValueError:
        return None
    if any(nota < 0 or nota > 10 for nota in notas):
        return "As notas devem estar entre 0 e 10. Envie três valores válidos."
    return f"A média de {notas[0]:g}, {notas[1]:g} e {notas[2]:g} é **{sum(notas) / 3:.2f}**."


def responder_pergunta(pergunta: str, tipo_usuario: str, usuario_id: int, query) -> dict:
    """Retorna a resposta e o assunto identificado para a API do chat."""
    pergunta = (pergunta or "").strip()
    if not pergunta:
        return {"resposta": "Escreva uma pergunta para que eu possa ajudar.", "assunto": "orientação"}
    if len(pergunta) > 1000:
        return {"resposta": "Envie uma pergunta de até 1.000 caracteres.", "assunto": "orientação"}

    texto = _normalizar(pergunta)
    if texto in {"oi", "ola", "bom dia", "boa tarde", "boa noite"} or any(saudacao in texto for saudacao in ("ola assistente", "oi assistente")):
        perfil = "aluno" if tipo_usuario == "aluno" else "professor" if tipo_usuario == "professor" else "equipe escolar"
        return {"resposta": f"Olá! Sou o assistente do sistema e posso ajudar você, {perfil}, com turmas, notas, frequência, matrículas e navegação.", "assunto": "boas-vindas"}

    media = _media_de_texto(pergunta) if any(palavra in texto for palavra in ("media", "calcule", "calcular")) else None
    if media:
        return {"resposta": media + "\n\nNo sistema, a média é calculada automaticamente ao lançar as três notas.", "assunto": "média"}

    if tipo_usuario == "aluno":
        if any(palavra in texto for palavra in ("minha nota", "minhas notas", "boletim", "nota de")):
            return {"resposta": "Estas são as notas vinculadas ao seu cadastro:\n" + _notas_do_aluno(query, usuario_id), "assunto": "notas"}
        if any(palavra in texto for palavra in ("minha frequencia", "minhas faltas", "minha presenca", "frequencia")):
            return {"resposta": "Sua frequência registrada:\n" + _frequencia_do_aluno(query, usuario_id), "assunto": "frequência"}
        if any(palavra in texto for palavra in ("minha turma", "minhas turmas", "qual turma", "professor")):
            return {"resposta": "Suas turmas ativas:\n" + _turmas_do_aluno(query, usuario_id), "assunto": "turmas"}
        if any(palavra in texto for palavra in ("parcela", "financeiro", "pagamento", "mensalidade", "vencimento")):
            return {"resposta": "Informações financeiras vinculadas ao seu cadastro:\n" + _financeiro_do_aluno(query, usuario_id) + "\n\nPara registrar um pagamento, procure a equipe responsável.", "assunto": "financeiro"}

    if tipo_usuario == "professor":
        if any(palavra in texto for palavra in ("minha turma", "minhas turmas", "turmas", "meus alunos", "quantos alunos")):
            return {"resposta": "Suas turmas ativas:\n" + _turmas_do_professor(query, usuario_id), "assunto": "turmas"}
        if any(palavra in texto for palavra in ("lancar nota", "registrar nota", "notas")):
            return {"resposta": "Para lançar notas, abra **Notas**, escolha uma das suas turmas, selecione o aluno e a matéria e informe as três notas (de 0 a 10). A média é calculada automaticamente. Você só pode lançar notas nas turmas vinculadas ao seu perfil.", "assunto": "notas"}
        if any(palavra in texto for palavra in ("frequencia", "presenca", "falta")):
            return {"resposta": "Para registrar frequência, abra a turma desejada e acesse **Frequência**. Informe a data da aula, marque os alunos presentes e confirme. Revise a turma e a data antes de salvar, pois esse registro impacta o acompanhamento acadêmico.", "assunto": "frequência"}

    if any(palavra in texto for palavra in ("cadastrar aluno", "cadastrar um aluno", "novo aluno", "cadastro de aluno")):
        return {"resposta": "Acesse **Alunos** e escolha **Adicionar aluno**. Preencha os dados obrigatórios e salve. Depois, em **Turmas**, abra a turma correta e use **Gerenciar alunos** para realizar a matrícula.", "assunto": "cadastro"}
    if any(palavra in texto for palavra in ("matricular", "matricula", "matrícula")):
        return {"resposta": "Antes da matrícula, confirme que o aluno, o curso, o professor e a turma já existem. Depois acesse **Turmas**, abra a turma desejada e use **Gerenciar alunos**. Verifique a capacidade da turma antes de confirmar.", "assunto": "matrícula"}
    if any(palavra in texto for palavra in ("cadastrar professor", "novo professor")):
        return {"resposta": "A equipe autorizada pode acessar **Professores** e escolher **Adicionar professor**. Após salvar, o professor poderá ser vinculado a uma turma durante o cadastro ou a gestão da turma.", "assunto": "cadastro"}
    if any(palavra in texto for palavra in ("criar turma", "nova turma")):
        return {"resposta": "Para criar uma turma, cadastre primeiro o curso e o professor. Em **Turmas**, escolha **Adicionar turma**, informe código, nome, curso, professor, período, horário e capacidade e confirme os dados.", "assunto": "turmas"}
    if any(palavra in texto for palavra in ("erro", "nao funciona", "não funciona", "problema", "falha")):
        return {"resposta": "Vamos investigar com segurança. Informe a mensagem completa exibida, a tela em que ocorreu e o que você tentou fazer. Não envie senha, CPF completo ou outros dados sensíveis. Como primeira tentativa, atualize a página, confirme o preenchimento dos campos obrigatórios e faça login novamente.", "assunto": "suporte"}
    if any(palavra in texto for palavra in ("ajuda", "o que voce faz", "o que você faz", "menu", "modulo", "módulo")):
        return {"resposta": "Posso orientar sobre cadastros, turmas, matrículas, notas, frequência, financeiro e relatórios. Alunos podem consultar suas próprias turmas, notas, frequência e parcelas; professores podem consultar suas turmas e receber orientação para lançar notas e frequência. Pergunte, por exemplo: “como matricular um aluno?” ou “minhas turmas”.", "assunto": "ajuda"}

    return {"resposta": "Posso ajudar com o uso do sistema. Tente perguntar sobre **cadastro de alunos**, **turmas**, **matrículas**, **notas**, **frequência**, **parcelas** ou descreva o erro que apareceu. Se a dúvida for sobre um dado específico, informe o contexto sem compartilhar senhas ou documentos.", "assunto": "orientação"}


INSTRUCOES_ASSISTENTE = """
Você é o Assistente Escolar da Gestão Escolar. Responda em português do Brasil,
de forma profissional, acolhedora e objetiva. Você ajuda alunos, professores e
equipe escolar a usar o sistema, mas nunca inventa dados, confirma alterações
que não foram realizadas ou pede senhas/CPF/documentos sensíveis.

O contexto verificado abaixo é a única fonte de dados da escola que você pode
afirmar. Respeite o perfil do usuário: dados de outros alunos não podem ser
expostos. Você não executa ações como lançar nota, alterar frequência, matrícula
ou pagamento; apenas orienta o usuário a usar as telas corretas.
""".strip()


def _extrair_texto_response_api(dados: dict) -> str:
    """Extrai o texto da resposta REST sem depender do SDK da OpenAI."""
    texto = dados.get("output_text")
    if isinstance(texto, str) and texto.strip():
        return texto.strip()
    partes = []
    for item in dados.get("output", []):
        for conteudo in item.get("content", []):
            if conteudo.get("type") in ("output_text", "text") and conteudo.get("text"):
                partes.append(conteudo["text"])
    return "\n".join(partes).strip()


def responder_com_ia(pergunta: str, tipo_usuario: str, usuario_id: int, query) -> dict:
    """Combina contexto autorizado local com a API da OpenAI quando configurada.

    A IA recebe somente a pergunta e uma resposta local verificada, nunca uma
    conexão direta com o banco de dados. Sem chave ou em caso de falha de rede,
    devolve a resposta local sem interromper o atendimento.
    """
    resposta_local = responder_pergunta(pergunta, tipo_usuario, usuario_id, query)
    chave = os.environ.get("OPENAI_API_KEY", "").strip()
    if not chave:
        return {**resposta_local, "provedor": "local", "ia_disponivel": False}

    modelo = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini").strip()
    entrada = f"""Perfil autenticado: {tipo_usuario}.

Pergunta do usuário:
{pergunta.strip()}

Contexto verificado pelo sistema (use estes dados como fonte de verdade):
{resposta_local['resposta']}

Responda à pergunta. Preserve todos os limites de segurança e privacidade.
Se o contexto não tiver o dado solicitado, explique como consultar no sistema.
"""
    try:
        resposta = requests.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {chave}",
                "Content-Type": "application/json",
            },
            json={
                "model": modelo,
                "instructions": INSTRUCOES_ASSISTENTE,
                "input": entrada,
                "max_output_tokens": 550,
            },
            timeout=20,
        )
        resposta.raise_for_status()
        texto = _extrair_texto_response_api(resposta.json())
        if texto:
            return {
                "resposta": texto,
                "assunto": resposta_local["assunto"],
                "provedor": "openai",
                "ia_disponivel": True,
            }
    except requests.RequestException:
        pass
    except (TypeError, ValueError):
        pass
    return {**resposta_local, "provedor": "local", "ia_disponivel": False}
