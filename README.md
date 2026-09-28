# Sport Store – Como atualizar o CSS (Tailwind)

O visual do site vem de `static/tailwind.css`, um arquivo **gerado** (não edite à mão).
As classes ficam nos templates (`templates/*.html`).

## Quando rodar o comando
Sempre que adicionar ou trocar classes do Tailwind nos templates.
(Não precisa para cadastrar camisas, mudar textos ou mexer no `app.py`.)

## Comando (na pasta do projeto)
```bash
./tailwindcss -i static/src.css -o static/tailwind.css --minify
```

## Depois
1. Testar: `python3 app.py`
2. Trocar o `?v=` no link do CSS do `index.html` (ex.: `?v=2` -> `?v=3`)
3. `git add static/tailwind.css` + commit + push
4. Render: Manual Deploy

## Primeira vez / máquina nova
```bash
curl -sLo tailwindcss https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-linux-x64
chmod +x tailwindcss
```
(O arquivo `tailwindcss` está no `.gitignore`; não vai para o GitHub.)

## Outros lembretes
- Dependências: `pip install -r requirements.txt` (inclui Flask-Compress)
- Start Command no Render: `gunicorn app:app --workers 2 --threads 4 --timeout 60`