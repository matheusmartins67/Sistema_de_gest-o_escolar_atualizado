"""Verificações de estrutura que não dependem das telas HTML ausentes."""

from pathlib import Path
import sys
import unittest
from uuid import uuid4
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from school_system.config import DATABASE_FILE, UPLOADS_DIR, database_path, ensure_runtime_directories
from school_system.web import app, get_db, initialize_database
from school_system.assistant_service import responder_com_ia


class ConfigurationTests(unittest.TestCase):
    def test_runtime_directories_are_available(self):
        ensure_runtime_directories()
        self.assertTrue(DATABASE_FILE.parent.exists())
        self.assertTrue(UPLOADS_DIR.exists())
        self.assertEqual(Path(database_path()), DATABASE_FILE)

    @patch.dict('os.environ', {'OPENAI_API_KEY': 'chave-de-teste', 'OPENAI_MODEL': 'modelo-teste'}, clear=False)
    @patch('school_system.assistant_service.requests.post')
    def test_assistant_uses_openai_responses_api_when_key_is_configured(self, post):
        resposta_http = Mock()
        resposta_http.json.return_value = {
            'output': [{'content': [{'type': 'output_text', 'text': 'Resposta gerada pela IA.'}]}]
        }
        resposta_http.raise_for_status.return_value = None
        post.return_value = resposta_http

        resposta = responder_com_ia('Como funciona a matrícula?', 'aluno', 1, lambda *args, **kwargs: [])
        self.assertEqual(resposta['provedor'], 'openai')
        self.assertEqual(resposta['resposta'], 'Resposta gerada pela IA.')
        self.assertEqual(post.call_args.args[0], 'https://api.openai.com/v1/responses')


class InitialPagesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        initialize_database()

    def setUp(self):
        self.client = app.test_client()

    def test_login_page_is_available(self):
        response = self.client.get('/login')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Entrar no sistema', response.data)

    def test_library_api_routes(self):
        response = self.client.get('/biblioteca')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'BIBLIOTECA ESCOLAR', response.data)
        self.assertIn(b'Livros dispon', response.data)

        response = self.client.get('/api/biblioteca')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['mensagem'], 'Seja bem-vindo à API da Biblioteca Escolar!')

        response = self.client.get('/api/biblioteca/livros')
        self.assertEqual(response.status_code, 200)
        self.assertGreater(response.get_json()['total'], 0)

        response = self.client.get('/api/biblioteca/livros/1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['livro']['id'], 1)

    def test_library_book_registration_is_planned(self):
        response = self.client.post(
            '/api/biblioteca/livros',
            json={'titulo': 'A Bolsa Amarela', 'autor': 'Lygia Bojunga'},
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.get_json()['livro_planejado']['titulo'], 'A Bolsa Amarela')

        response = self.client.post('/api/biblioteca/livros', json={'titulo': 'Sem autor'})
        self.assertEqual(response.status_code, 400)

    def test_library_catalog_and_loan_work_for_authenticated_user(self):
        self._authenticate_as_admin()
        identificador = uuid4().hex[:8]
        response = self.client.post('/biblioteca/livro/novo', data={
            'titulo': f'Livro {identificador}',
            'autor': 'Autor de teste',
            'categoria': 'Teste',
            'quantidade_total': '1',
        }, follow_redirects=False)
        self.assertEqual(response.status_code, 302)

        conexao = get_db()
        livro = conexao.execute('SELECT id FROM livros_biblioteca WHERE titulo = ?', (f'Livro {identificador}',)).fetchone()
        conexao.close()
        self.assertIsNotNone(livro)

        response = self.client.post(f'/biblioteca/livro/{livro["id"]}/emprestar', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Empr', response.data)

        conexao = get_db()
        emprestimo = conexao.execute('''
        SELECT id FROM emprestimos_biblioteca
        WHERE livro_id = ? AND usuario_id = 1 AND usuario_tipo = 'admin' AND status = 'emprestado'
        ''', (livro['id'],)).fetchone()
        conexao.close()
        self.assertIsNotNone(emprestimo)

        response = self.client.post(f'/biblioteca/emprestimo/{emprestimo["id"]}/devolver', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Devolu', response.data)

    def test_initial_admin_can_log_in(self):
        response = self.client.post(
            '/login',
            data={'email': 'admin@escola.com', 'senha': 'Mudar@123'},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Seja bem-vindo ao Sistema de Gest', response.data)

    def test_assistant_requires_login_and_is_available_to_logged_user(self):
        response = self.client.get('/assistente', follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['Location'], '/login')

        self._authenticate_as_admin()
        response = self.client.get('/assistente')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Assistente', response.data)

        response = self.client.post('/api/assistente/perguntar', json={
            'pergunta': 'Como cadastrar um aluno?'
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('Alunos', response.get_json()['resposta'])

    def test_student_assistant_only_returns_own_data(self):
        identificador = uuid4().hex[:10]
        conexao = get_db()
        cursor = conexao.cursor()
        cursor.execute('''
        INSERT INTO alunos (nome, email, cpf, senha, matricula, ativo)
        VALUES (?, ?, ?, 'hash', ?, 1)
        ''', (f'Aluno privado {identificador}', f'privado-{identificador}@teste.local', f'PV{identificador}', f'AL{identificador}'))
        aluno_id = cursor.lastrowid
        cursor.execute('''
        INSERT INTO alunos (nome, email, cpf, senha, matricula, ativo)
        VALUES (?, ?, ?, 'hash', ?, 1)
        ''', (f'Outro aluno {identificador}', f'outro-{identificador}@teste.local', f'OU{identificador}', f'OU{identificador}'))
        outro_aluno_id = cursor.lastrowid
        cursor.execute('INSERT INTO cursos (nome, ativo) VALUES (?, 1)', (f'Curso privado {identificador}',))
        curso_id = cursor.lastrowid
        cursor.execute('INSERT INTO modulos (curso_id, nome, ordem) VALUES (?, ?, 1)', (curso_id, 'Matemática'))
        modulo_id = cursor.lastrowid
        cursor.execute('''
        INSERT INTO professores (nome, email, cpf, senha, matricula, ativo)
        VALUES (?, ?, ?, 'hash', ?, 1)
        ''', (f'Professor privado {identificador}', f'profpriv-{identificador}@teste.local', f'PR{identificador}', f'P{identificador}'))
        professor_id = cursor.lastrowid
        cursor.execute('''
        INSERT INTO turmas (codigo, nome, curso_id, professor_id, capacidade, ativa)
        VALUES (?, ?, ?, ?, 30, 1)
        ''', (f'X{identificador}', 'Turma Privada', curso_id, professor_id))
        turma_id = cursor.lastrowid
        cursor.execute('INSERT INTO matriculas (aluno_id, turma_id, status) VALUES (?, ?, "ativa")', (aluno_id, turma_id))
        matricula_id = cursor.lastrowid
        cursor.execute('INSERT INTO matriculas (aluno_id, turma_id, status) VALUES (?, ?, "ativa")', (outro_aluno_id, turma_id))
        cursor.execute('''
        INSERT INTO notas (matricula_id, modulo_id, primeira_nota, segunda_nota, terceira_nota, media_final)
        VALUES (?, ?, 7, 8, 9, 8)
        ''', (matricula_id, modulo_id))
        conexao.commit()
        conexao.close()

        with self.client.session_transaction() as session:
            session['usuario_id'] = aluno_id
            session['tipo_usuario'] = 'aluno'
        response = self.client.post('/api/assistente/perguntar', json={'pergunta': 'Minhas notas'})
        self.assertEqual(response.status_code, 200)
        resposta = response.get_json()['resposta']
        self.assertIn('Matemática', resposta)
        self.assertNotIn(f'Outro aluno {identificador}', resposta)

    def test_reports_are_available_to_authorized_user(self):
        with self.client.session_transaction() as session:
            session['usuario_id'] = 1
            session['tipo_usuario'] = 'admin'

        response = self.client.get('/relatorios')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Relat', response.data)

    def _authenticate_as_admin(self):
        with self.client.session_transaction() as session:
            session['usuario_id'] = 1
            session['tipo_usuario'] = 'admin'

    def test_old_room_links_redirect_to_turmas(self):
        self._authenticate_as_admin()
        response = self.client.get('/salas', follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['Location'], '/turmas')

        response = self.client.get('/turmas')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Adicionar turma', response.data)

    def test_student_can_be_added_and_listed(self):
        self._authenticate_as_admin()
        identificador = uuid4().hex[:10]
        nome = f'Aluno {identificador}'
        response = self.client.post('/aluno/novo', data={
            'nome': nome,
            'email': f'{identificador}@teste.local',
            'cpf': identificador,
            'telefone': '11999999999',
            'data_nascimento': '2000-01-01',
            'senha': 'Senha@123',
        }, follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['Location'], '/alunos')

        response = self.client.get('/alunos')
        self.assertEqual(response.status_code, 200)
        self.assertIn(nome.encode(), response.data)

    def test_teacher_can_be_added_and_listed(self):
        self._authenticate_as_admin()
        identificador = uuid4().hex[:10]
        nome = f'Professor {identificador}'
        response = self.client.post('/professor/novo', data={
            'nome': nome,
            'email': f'{identificador}@teste.local',
            'cpf': f'P{identificador}',
            'formacao': 'Licenciatura',
            'especialidade': 'Ciências',
            'senha': 'Senha@123',
        }, follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['Location'], '/professores')

        response = self.client.get('/professores')
        self.assertEqual(response.status_code, 200)
        self.assertIn(nome.encode(), response.data)

    def test_course_creates_its_subjects(self):
        self._authenticate_as_admin()
        identificador = uuid4().hex[:10]
        response = self.client.post('/curso/novo', data={
            'nome': f'Curso {identificador}',
            'descricao': 'Curso de teste',
            'duracao_meses': '12',
            'valor': '199.90',
            'disciplinas': 'Português\nMatemática',
        }, follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['Location'], '/cursos')

        conexao = get_db()
        curso = conexao.execute('SELECT id FROM cursos WHERE nome = ?', (f'Curso {identificador}',)).fetchone()
        total_modulos = conexao.execute('SELECT COUNT(*) FROM modulos WHERE curso_id = ?', (curso['id'],)).fetchone()[0]
        conexao.close()
        self.assertEqual(total_modulos, 2)

    def test_student_can_be_added_to_existing_turma(self):
        identificador = uuid4().hex[:10]
        conexao = get_db()
        cursor = conexao.cursor()
        cursor.execute('INSERT INTO cursos (nome, ativo) VALUES (?, 1)', (f'Curso turma {identificador}',))
        curso_id = cursor.lastrowid
        cursor.execute('''
        INSERT INTO professores (nome, email, cpf, senha, matricula, ativo)
        VALUES (?, ?, ?, 'hash', ?, 1)
        ''', (f'Professor turma {identificador}', f'pt-{identificador}@teste.local', f'TP{identificador}', f'TPR{identificador}'))
        professor_id = cursor.lastrowid
        cursor.execute('''
        INSERT INTO turmas (codigo, nome, curso_id, professor_id, capacidade, ativa)
        VALUES (?, ?, ?, ?, 2, 1)
        ''', (f'T{identificador}', f'Turma {identificador}', curso_id, professor_id))
        turma_id = cursor.lastrowid
        cursor.execute('''
        INSERT INTO alunos (nome, email, cpf, senha, matricula, ativo)
        VALUES (?, ?, ?, 'hash', ?, 1)
        ''', (f'Aluno turma {identificador}', f'at-{identificador}@teste.local', f'TA{identificador}', f'TAL{identificador}'))
        aluno_id = cursor.lastrowid
        conexao.commit()
        conexao.close()

        self._authenticate_as_admin()
        response = self.client.post(f'/turma/{turma_id}/alunos', data={'aluno_id': aluno_id}, follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['Location'], f'/turma/{turma_id}/alunos')

        conexao = get_db()
        matricula = conexao.execute('SELECT id FROM matriculas WHERE aluno_id = ? AND turma_id = ?', (aluno_id, turma_id)).fetchone()
        conexao.close()
        self.assertIsNotNone(matricula)

    def test_grade_is_created_then_updated_with_average(self):
        identificador = uuid4().hex[:10]
        conexao = get_db()
        cursor = conexao.cursor()
        cursor.execute('INSERT INTO cursos (nome, ativo) VALUES (?, 1)', (f'Curso {identificador}',))
        curso_id = cursor.lastrowid
        cursor.execute('INSERT INTO modulos (curso_id, nome, ordem) VALUES (?, ?, 1)', (curso_id, f'Módulo {identificador}'))
        modulo_id = cursor.lastrowid
        cursor.execute('''
        INSERT INTO professores (nome, email, cpf, senha, matricula, ativo)
        VALUES (?, ?, ?, 'hash', ?, 1)
        ''', (f'Professor {identificador}', f'prof-{identificador}@teste.local', f'PP{identificador}', f'PRF{identificador}'))
        professor_id = cursor.lastrowid
        cursor.execute('''
        INSERT INTO turmas (codigo, nome, curso_id, professor_id, capacidade, ativa)
        VALUES (?, ?, ?, ?, 30, 1)
        ''', (f'T{identificador}', f'Turma {identificador}', curso_id, professor_id))
        turma_id = cursor.lastrowid
        cursor.execute('''
        INSERT INTO alunos (nome, email, cpf, senha, matricula, ativo)
        VALUES (?, ?, ?, 'hash', ?, 1)
        ''', (f'Aluno {identificador}', f'aluno-{identificador}@teste.local', f'AA{identificador}', f'ALN{identificador}'))
        aluno_id = cursor.lastrowid
        cursor.execute('INSERT INTO matriculas (aluno_id, turma_id, status) VALUES (?, ?, "ativa")', (aluno_id, turma_id))
        matricula_id = cursor.lastrowid
        conexao.commit()
        conexao.close()

        self._authenticate_as_admin()
        dados = {
            'matricula_id': matricula_id,
            'modulo_id': modulo_id,
            'primeira_nota': '8',
            'segunda_nota': '7',
            'terceira_nota': '9',
        }
        response = self.client.post(f'/turma/{turma_id}/notas', data=dados, follow_redirects=False)
        self.assertEqual(response.status_code, 302)

        dados['terceira_nota'] = '10'
        response = self.client.post(f'/turma/{turma_id}/notas', data=dados, follow_redirects=False)
        self.assertEqual(response.status_code, 302)

        conexao = get_db()
        nota = conexao.execute('SELECT COUNT(*) AS total, media_final FROM notas WHERE matricula_id = ? AND modulo_id = ?', (matricula_id, modulo_id)).fetchone()
        conexao.close()
        self.assertEqual(nota['total'], 1)
        self.assertEqual(nota['media_final'], 8.33)


if __name__ == "__main__":
    unittest.main()
