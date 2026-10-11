#!/usr/bin/env sh
# Оборачивает landing/index.html в полноценный HTML-документ для GitHub Pages -> _site/index.html
set -e
mkdir -p _site
{
  printf '<!doctype html>\n<html lang="ru">\n<head>\n<meta charset="utf-8">\n'
  printf '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
  printf '<meta name="description" content="Быстрый поиск билетов на поезд Орёл — Москва на сайте РЖД">\n'
  printf '<style>body{margin:0}img{max-width:100%%}[hidden]{display:none!important}</style>\n</head>\n<body>\n'
  # адрес API подставляется из переменной API_URL (пусто = тот же сервер, /api/trains)
  sed "s|__API_URL__|${API_URL:-}|g" landing/index.html
  printf '\n</body>\n</html>\n'
} > _site/index.html
echo "built _site/index.html"
