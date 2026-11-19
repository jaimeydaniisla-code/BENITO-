#!/bin/bash
# Publica lo que haya cambiado el robot del directo, reintentando si el otro robot ha subido datos a la vez.
F="envivo.json datos.json cuotas.json modelo_cuotas/picks_log.jsonl modelo_cuotas/peticiones.json modelo_cuotas/historico_cuotas.jsonl modelo_cuotas/catalogo_mercados.json"
for f in $F; do [ -f "$f" ] && git add "$f"; done
git diff --cached --quiet && exit 0
git commit -qm "Directo"
for i in 1 2 3; do
  git pull -q --rebase origin main && git push -q && exit 0
  git rebase --abort 2>/dev/null || true
  mkdir -p /tmp/s; for f in $F; do [ -f "$f" ] && cp "$f" /tmp/s/$(basename $f); done
  git fetch -q origin main && git reset -q --hard origin/main
  for f in $F; do [ -f /tmp/s/$(basename $f) ] && cp /tmp/s/$(basename $f) "$f"; done
  git checkout -q origin/main -- datos.json && python modelo_cuotas/aplicar_previas.py
  for f in $F; do [ -f "$f" ] && git add "$f"; done
  git diff --cached --quiet && exit 0
  git commit -qm "Directo"
  sleep 5
done
exit 1
