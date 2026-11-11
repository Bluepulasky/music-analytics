#!/usr/bin/env python3
"""
navidrome_dashboard.py

Consulta la API de Navidrome (search3, paginado) y escupe un único archivo
navidrome_library.html con el dashboard (JS vanilla + Plotly.js).
Sin Flask, sin CSV intermedio, sin pandas: los datos van embebidos en el HTML
y todos los filtros/estadísticas se calculan en el navegador.

Uso:
    python navidrome_dashboard.py          # genera navidrome_library.html
    python navidrome_dashboard.py --open   # además lo abre en el navegador

Requiere config.local.yaml junto al script:
    navidrome:
      user: ...
      password: ...
"""
import hashlib
import json
import os
import random
import string
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

import requests
import yaml

NAVIDROME_URL = "http://192.168.1.99:4533"
BATCH_SIZE = 500

# False: Plotly se carga desde el CDN (necesita internet al abrir el HTML).
# True: lo embebe en el archivo (necesita `pip install plotly`, suma ~4 MB).
EMBED_PLOTLY = True
PLOTLY_CDN = "https://cdn.plot.ly/plotly-2.35.2.min.js"

BASE_DIR = Path(__file__).resolve().parent if "__file__" in globals() else Path(os.getcwd())
OUTPUT = BASE_DIR / "index.html"

# Orden de columnas que viaja al HTML (el JS las lee por nombre).
COLS = [
    "title", "artist", "album", "albumArtist", "albumId", "year", "genre",
    "duration", "bitRate", "size", "suffix",
    "playCount", "played", "starred", "userRating", "created",
    "bitDepth", "samplingRate",
]


def load_credentials():
    cfg_path = BASE_DIR / "config.local.yaml"
    if not cfg_path.exists():
        sys.exit(f"No encuentro {cfg_path}")
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    nd = cfg.get("navidrome", {})
    if not nd.get("user") or not nd.get("password"):
        sys.exit("Faltan navidrome.user / navidrome.password en config.local.yaml")
    return nd["user"], nd["password"]


def auth_params(user, password):
    salt = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    token = hashlib.md5(f"{password}{salt}".encode()).hexdigest()
    return dict(u=user, t=token, s=salt, v="1.16.1", c="navdash", f="json")


def fetch_songs(params):
    songs, seen, offset = [], set(), 0
    while True:
        r = requests.get(
            f"{NAVIDROME_URL}/rest/search3",
            params={**params, "query": "", "artistCount": 0, "albumCount": 0,
                    "songCount": BATCH_SIZE, "songOffset": offset},
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()["subsonic-response"]
        if data.get("status") != "ok":
            raise RuntimeError(f"Navidrome error: {data.get('error')}")

        batch = data.get("searchResult3", {}).get("song", [])
        if not batch:
            break

        new = [s for s in batch if s.get("id") not in seen]
        if not new:  # el servidor ignoró el offset: evitamos loop infinito
            break
        seen.update(s.get("id") for s in new)
        songs.extend(new)
        offset += len(batch)

    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - Total: {len(songs)} canciones")
    return songs


def to_row(s):
    album_artist = s.get("displayAlbumArtist") or s.get("albumArtist") or ""
    return [
        s.get("title", ""), s.get("artist", ""), s.get("album", ""),
        album_artist, s.get("albumId", ""), s.get("year", 0), s.get("genre", ""),
        s.get("duration", 0), s.get("bitRate", 0), s.get("size", 0), s.get("suffix", ""),
        s.get("playCount", 0), s.get("played", ""), s.get("starred", ""),
        s.get("userRating", 0), s.get("created", ""),
        s.get("bitDepth", 0), s.get("samplingRate", 0),
    ]


def plotly_tag():
    if EMBED_PLOTLY:
        try:
            from plotly.offline import get_plotlyjs
            return f"<script>{get_plotlyjs()}</script>"
        except ImportError:
            print("EMBED_PLOTLY=True pero falta `pip install plotly`; uso el CDN.")
    return f'<script src="{PLOTLY_CDN}"></script>'


def build_html(songs):
    payload = {
        "generated": datetime.now().isoformat(timespec="minutes"),
        "cols": COLS,
        "rows": [to_row(s) for s in songs],
    }
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    blob = blob.replace("</", "<\\/").replace("<!--", "<\\!--")
    return TEMPLATE.replace("/*@@PLOTLY@@*/", plotly_tag()).replace("/*@@DATA@@*/", blob)


def main():
    user, password = load_credentials()
    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - Pidiendo la biblioteca a {NAVIDROME_URL} ...")
    songs = fetch_songs(auth_params(user, password))
    if not songs:
        sys.exit("Navidrome no devolvió canciones.")
    OUTPUT.write_text(build_html(songs), encoding="utf-8")
    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - Listo → {OUTPUT}")
    if "--open" in sys.argv:
        webbrowser.open(OUTPUT.as_uri())


TEMPLATE = r"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Biblioteca musical</title>
/*@@PLOTLY@@*/
<style>
:root{--bg:#15121a;--panel:#1e1a25;--panel2:#292331;--line:#352f41;--text:#ece6dc;--dim:#a39cae;--amber:#e8a33d;--teal:#4fb3a9;--rose:#d9647a}
*{box-sizing:border-box}
html{scroll-behavior:smooth;scroll-padding-top:150px}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;-webkit-font-smoothing:antialiased}
h1,h2,h3,.big,.kpi .v,.stat{font-family:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;font-weight:600;letter-spacing:-.01em}
a{color:var(--amber);text-decoration:none}
a:hover{text-decoration:underline}
:focus-visible{outline:2px solid var(--amber);outline-offset:2px}
.top{display:flex;flex-wrap:wrap;gap:12px 32px;justify-content:space-between;align-items:flex-end;padding:26px 24px 14px;max-width:1500px;margin:0 auto}
.top h1{margin:0;font-size:30px}
.meta{margin:2px 0 0;color:var(--dim);font-size:13px}
nav{display:flex;flex-wrap:wrap;gap:6px 18px;font-size:14px}
.filters{position:sticky;top:0;z-index:20;background:rgba(21,18,26,.96);backdrop-filter:blur(6px);border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
.filters>summary{cursor:pointer;padding:8px 24px;font-size:14px;list-style:none;display:flex;justify-content:space-between;gap:12px;max-width:1500px;margin:0 auto}
.filters>summary::-webkit-details-marker{display:none}
#count{color:var(--amber)}
.f-row{display:flex;flex-wrap:wrap;gap:10px 18px;align-items:flex-end;padding:4px 24px 12px;max-width:1500px;margin:0 auto}
.f{display:flex;flex-direction:column;gap:3px;font-size:12.5px;color:var(--dim);min-width:0}
.f.check{flex-direction:row;align-items:center;gap:6px;color:var(--text);padding-bottom:6px}
.pair{display:flex;gap:6px}
input,select,button{font:inherit;font-size:13px}
input,select{background:var(--panel2);color:var(--text);border:1px solid var(--line);border-radius:6px;padding:6px 8px}
input[type=number]{width:84px}
.pick input{width:190px}
.chips{display:flex;flex-wrap:wrap;gap:4px;max-width:260px}
.chip{background:var(--panel2);border:1px solid var(--line);color:var(--text);border-radius:999px;padding:2px 10px;font-size:12px;cursor:pointer}
.chip[aria-pressed=true]{background:var(--amber);border-color:var(--amber);color:#1b1410}
.chip small{opacity:.65}
.btn{background:transparent;border:1px solid var(--amber);color:var(--amber);border-radius:6px;padding:6px 12px;cursor:pointer}
.btn:hover{background:var(--amber);color:#1b1410}
main{max-width:1500px;margin:0 auto;padding:20px 24px 40px}
section{margin-top:44px}
.shead{display:flex;flex-wrap:wrap;gap:8px 24px;justify-content:space-between;align-items:flex-end;margin-bottom:14px}
.shead h2{margin:0;font-size:26px}
.shead p{margin:2px 0 0;color:var(--dim);font-size:14px;max-width:70ch}
.seg{display:flex;border:1px solid var(--line);border-radius:8px;overflow:hidden}
.seg button{background:var(--panel);color:var(--dim);border:0;padding:6px 14px;cursor:pointer}
.seg button[aria-pressed=true]{background:var(--amber);color:#1b1410}
.hero{position:relative;overflow:hidden;background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:30px 34px;margin-bottom:14px}
.hero::after{content:"";position:absolute;right:-110px;top:50%;width:380px;height:380px;transform:translateY(-50%);border-radius:50%;opacity:.55;pointer-events:none;transparent 1px 7px)}
.hero>*{position:relative;z-index:1}
.hero .lab{color:var(--dim);font-size:14px}
.big{font-size:clamp(34px,6vw,62px);line-height:1.08;margin:4px 0}
.big span{color:var(--amber)}
.hero .row{display:flex;flex-wrap:wrap;gap:6px 40px;align-items:baseline}
.hero .sz{font-size:clamp(22px,3vw,32px);font-family:"Iowan Old Style",Georgia,serif}
.hero .sub2{color:var(--dim);font-size:13px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px}
.kpi{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.kpi .l{color:var(--dim);font-size:13px}
.kpi .v{font-size:28px;line-height:1.2}
.kpi .s{font-size:12px;color:var(--dim)}
.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}
.w2{grid-column:span 2}.w3{grid-column:span 3}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px 16px 12px;min-width:0}
.card h3{margin:0;font-size:18px}
.sub{margin:2px 0 8px;color:var(--dim);font-size:12.5px;min-height:1em}
.chart{width:100%}
.empty{display:flex;align-items:center;justify-content:center;height:100%;min-height:120px;color:var(--dim);font-size:13px}
.rank{margin:6px 0 0;padding:0;list-style:none}
.rank li{display:flex;justify-content:space-between;gap:12px;padding:8px 0;border-bottom:1px solid var(--line)}
.rank li span{color:var(--dim)}
.stat{font-size:44px;line-height:1.1}
.dim{color:var(--dim)}
.ind{display:grid;grid-template-columns:1fr;gap:10px}
.ind div{border-bottom:1px solid var(--line);padding-bottom:8px}
.ind b{font-family:"Iowan Old Style",Georgia,serif;font-size:24px;margin-right:8px}
.ind small{display:block;color:var(--dim);font-size:12px}
table{width:100%;border-collapse:collapse}
th,td{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left;font-size:13px;vertical-align:top}
th{position:sticky;top:0;background:var(--panel);color:var(--dim);font-weight:600;white-space:nowrap}
th[data-k]{cursor:pointer}
th.s{color:var(--amber)}
.n{text-align:right;font-variant-numeric:tabular-nums}
.twrap{overflow:auto;max-height:440px}
.tbar{display:flex;gap:12px;align-items:center;margin-bottom:8px}
.tbar input{flex:1;min-width:0;max-width:300px}
.tcount{color:var(--dim);font-size:12.5px}
.tpager{display:flex;gap:10px;align-items:center;justify-content:flex-end;margin-top:8px;font-size:12.5px;color:var(--dim)}
.tpager button{background:var(--panel2);color:var(--text);border:1px solid var(--line);border-radius:6px;padding:4px 10px;cursor:pointer}
.tpager button:disabled{opacity:.4;cursor:default}
.mk{display:inline-block;background:rgba(217,100,122,.16);color:#f0a3b2;border-radius:4px;padding:1px 6px;font-size:11.5px;margin:0 4px 2px 0}
.ft .bar{background:var(--panel2);border-radius:4px;height:8px;min-width:90px}
.ft .bar i{display:block;height:100%;border-radius:4px;background:var(--teal)}
.note{color:var(--dim);font-size:12.5px;margin:10px 0 0}
footer{max-width:1500px;margin:0 auto;padding:0 24px 60px;color:var(--dim);font-size:13px}
footer summary{cursor:pointer;color:var(--text)}
footer li{margin:4px 0}
@media(max-width:1100px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}.w3{grid-column:span 2}}
@media(max-width:760px){
  .grid{grid-template-columns:minmax(0,1fr)}.w2,.w3{grid-column:auto}
  .filters{position:static}.top,.f-row,main,footer{padding-left:14px;padding-right:14px}
  .hero{padding:22px 18px}.hero::after{opacity:.2}
  .pick input{width:100%}.f{flex:1 1 140px}
}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
</style>
</head>
<body>
<header class="top">
  <div>
    <h1>Biblioteca musical</h1>
    <p class="meta" id="meta"></p>
  </div>
  <nav>
    <a href="#resumen">Resumen</a><a href="#tiempo">Tiempo</a><a href="#musica">Música</a><a href="#plays">Reproducciones</a><a href="#formatos">Formatos</a><a href="#metadatos">Metadatos</a><a href="#coleccion">Colección</a>
  </nav>
</header>

<details class="filters" id="filters" open>
  <summary><span>Filtros</span><span id="count"></span></summary>
  <div class="f-row">
    <label class="f">Años<span class="pair"><input id="yMin" type="number" placeholder="desde"><input id="yMax" type="number" placeholder="hasta"></span></label>
    <label class="f">Bitrate (kbps)<span class="pair"><input id="bMin" type="number" placeholder="mín."><input id="bMax" type="number" placeholder="máx."></span></label>
    <div class="f pick"><label for="inArtists">Artista</label><input id="inArtists" list="dlArtists" placeholder="Buscar y elegir" autocomplete="off"><datalist id="dlArtists"></datalist><div class="chips" id="chArtists"></div></div>
    <div class="f pick"><label for="inAlbums">Álbum</label><input id="inAlbums" list="dlAlbums" placeholder="Buscar y elegir" autocomplete="off"><datalist id="dlAlbums"></datalist><div class="chips" id="chAlbums"></div></div>
    <div class="f pick"><label for="inGenres">Género</label><input id="inGenres" list="dlGenres" placeholder="Buscar y elegir" autocomplete="off"><datalist id="dlGenres"></datalist><div class="chips" id="chGenres"></div></div>
    <div class="f"><span>Formato</span><div class="chips" id="fmts"></div></div>
    <label class="f">Metadatos<select id="sComp"><option value="all">Todos</option><option value="complete">Completos</option><option value="incomplete">Incompletos</option><option value="nogenre">Sin género</option><option value="noyear">Sin año</option></select></label>
    <label class="f">Reproducciones<select id="sPlay"><option value="all">Todas</option><option value="played">Con reproducciones</option><option value="never">Sin reproducir</option></select></label>
    <label class="f check"><input type="checkbox" id="cNorm">Géneros normalizados</label>
    <button class="btn" id="clear" type="button">Limpiar filtros</button>
  </div>
</details>

<main>
  <section id="resumen">
    <div class="hero">
      <div class="lab">Duración total de la biblioteca</div>
      <div class="big" id="kDur"></div>
      <div class="sub2" id="kDurSub"></div>
      <div class="row" style="margin-top:14px"><span class="sz" id="kSize"></span><span class="sub2" id="kSizeSub"></span></div>
    </div>
    <div class="kpis" id="kpis"></div>
  </section>
  <div id="sections"></div>
</main>

<footer>
  <details>
    <summary>Cómo se calcula cada cosa</summary>
    <ul>
      <li>Todo sale del inventario que devuelve Navidrome; no se completan ni se corrigen datos. Cada fila es un archivo (registro); artistas y álbumes se cuentan como valores únicos.</li>
      <li>Álbum único: el id de álbum de Navidrome; si no viniera, la combinación artista + álbum. Así dos «Greatest Hits» de artistas distintos no se mezclan.</li>
      <li>Vacío: campo sin valor, año o números en 0, o los marcadores [Unknown Artist] / [Unknown Album] que Navidrome pone cuando falta el dato. Un valor poco habitual no se considera error.</li>
      <li>Metadatos completos: los 9 campos de la lista (Title, Artist, Album, Year, Genre, Duration, Bitrate, Size, Suffix) tienen valor.</li>
      <li>Géneros: se muestran tal cual están en los metadatos. La vista normalizada agrupa por minúsculas, espacios y guiones, solo para estudiar variantes; no modifica nada.</li>
      <li>Lossless: flac, wav, aiff, ape, wv, alac, dsf. Con pérdida: mp3, ogg, opus, aac, wma. Ambiguo: m4a/mp4, porque el contenedor puede llevar AAC o ALAC y el inventario no lo indica.</li>
      <li>Períodos: hasta 1969, 1970–1989, 1990–2009 y 2010 en adelante. Son cortes por año definidos acá, no estilos.</li>
      <li>Tamaños en GB decimales (1 GB = 1.000.000.000 bytes). Posible duplicado: mismo título, artista y álbum ignorando mayúsculas y acentos.</li>
      <li>Reproducciones, favoritas y valoraciones son las del usuario con el que se consultó la API. La fecha de alta es cuando Navidrome indexó el archivo.</li>
    </ul>
  </details>
</footer>

<script>
(function(){
'use strict';
const RAW = /*@@DATA@@*/;

/* ---------- utilidades ---------- */
const $ = id => document.getElementById(id);
const esc = s => String(s==null?'':s).replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const NF = new Intl.NumberFormat('es-ES',{useGrouping:'always',maximumFractionDigits:0});
const N1 = new Intl.NumberFormat('es-ES',{useGrouping:'always',maximumFractionDigits:1});
const fi = n => NF.format(n), f1 = n => N1.format(n);
const pc = (a,b) => b>0 ? 100*a/b : 0;
const pcs = (a,b) => f1(pc(a,b))+'%';
const sum = (a,f) => { let s=0; for(const x of a) s+=f(x); return s; };
const mean = a => a.length ? a.reduce((x,y)=>x+y,0)/a.length : 0;
const median = a => { if(!a.length) return 0; const s=a.slice().sort((x,y)=>x-y), m=s.length>>1; return s.length%2 ? s[m] : (s[m-1]+s[m])/2; };
const trunc = (s,n) => s.length>n ? s.slice(0,n-1)+'…' : s;
const mmss = s => Math.floor(s/60)+':'+String(Math.floor(s%60)).padStart(2,'0');
const mkey = d => d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0');
const setText = (id,t) => { const e=$(id); if(e) e.textContent=t; };
const setSub = (id,t) => setText(id+'-sub',t);
const frac = (a,b,w) => fi(a)+' de '+fi(b)+' '+(w||'canciones');
function countBy(arr,kf){ const m=new Map(); for(const x of arr){ const k=kf(x); if(k==null||k==='') continue; m.set(k,(m.get(k)||0)+1); } return m; }
const topN = (m,n) => [...m.entries()].sort((a,b)=>b[1]-a[1]||String(a[0]).localeCompare(String(b[0]),'es')).slice(0,n);
const norm = s => s.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/\s+/g,' ').trim();

/* ---------- preparación de datos ---------- */
const PLACE = new Set(['[unknown artist]','[unknown album]','[unknown]']);
const clean = v => { const s = v==null ? '' : String(v).trim(); return PLACE.has(s.toLowerCase()) ? '' : s; };
const asDate = v => { if(!v) return null; const d=new Date(v); return isNaN(d) || d.getFullYear()<1971 ? null : d; };
const normGenre = g => g.toLowerCase().replace(/[\s_\-\/]+/g,' ').trim();
const LOSSLESS = new Set(['flac','wav','aiff','aif','ape','wv','alac','dsf','dff','tta']);
const LOSSY = new Set(['mp3','ogg','oga','opus','aac','wma','mpc']);
const AMBIG = new Set(['m4a','mp4','m4b']);
const clsOf = f => LOSSLESS.has(f) ? 'Lossless' : LOSSY.has(f) ? 'Con pérdida' : AMBIG.has(f) ? 'Ambiguo' : 'Otro';
const FIELDS = [['title','Title'],['artist','Artist'],['album','Album'],['year','Year'],['genre','Genre'],['duration','Duration'],['bitRate','Bitrate'],['size','Size'],['suffix','Suffix']];
const FN = Object.fromEntries(FIELDS);

const CI = {}; RAW.cols.forEach((c,i)=>CI[c]=i);
const R = RAW.rows.map((r,i)=>{
  const g = k => r[CI[k]];
  const title=clean(g('title')), artist=clean(g('artist')), album=clean(g('album')), genre=clean(g('genre'));
  const fmt=clean(g('suffix')).toLowerCase();
  const year=+g('year')||0, dur=+g('duration')||0, br=+g('bitRate')||0, sz=+g('size')||0;
  const miss=[];
  if(!title) miss.push('title'); if(!artist) miss.push('artist'); if(!album) miss.push('album');
  if(!(year>0)) miss.push('year'); if(!genre) miss.push('genre'); if(!(dur>0)) miss.push('duration');
  if(!(br>0)) miss.push('bitRate'); if(!(sz>0)) miss.push('size'); if(!fmt) miss.push('suffix');
  return {
    i, title, artist, album, albumArtist: clean(g('albumArtist')),
    akey: album ? (g('albumId') || artist+'\u0001'+album) : null,
    yr: year>0 ? year : null, dec: year>0 ? Math.floor(year/10)*10 : null,
    genre, genN: genre ? normGenre(genre) : '',
    dur, br, sz, fmt: fmt||'(vacío)', cls: clsOf(fmt),
    plays: +g('playCount')||0, played: asDate(g('played')), starred: !!g('starred'),
    rating: +g('userRating')||0, created: asDate(g('created')),
    bd: +g('bitDepth')||0, sr: +g('samplingRate')||0,
    miss, complete: miss.length===0
  };
});

const AL = new Map();
for(const o of R){
  if(!o.akey) continue;
  let a = AL.get(o.akey);
  if(!a){ a={name:o.album, aa:o.albumArtist, ar:new Map()}; AL.set(o.akey,a); }
  if(!a.aa && o.albumArtist) a.aa=o.albumArtist;
  if(o.artist) a.ar.set(o.artist,(a.ar.get(o.artist)||0)+1);
}
for(const a of AL.values()){
  const who = a.aa || (topN(a.ar,1)[0]||[''])[0];
  a.label = who ? a.name+' ('+who+')' : a.name;
}
for(const o of R) o.alabel = o.akey ? AL.get(o.akey).label : '';

const GN = new Map();
for(const o of R){ if(!o.genre) continue; let m=GN.get(o.genN); if(!m){ m=new Map(); GN.set(o.genN,m); } m.set(o.genre,(m.get(o.genre)||0)+1); }
const GNAME = new Map(); for(const [k,m] of GN) GNAME.set(k, topN(m,1)[0][0]);

const PAL = ['#e8a33d','#4fb3a9','#9a86e0','#d9647a','#5fa8e8','#9fc062','#d98a5f','#c07fb5','#7fc4d6','#bfae6a'];
const CLSCOL = {'Lossless':'#4fb3a9','Con pérdida':'#d9647a','Ambiguo':'#e8a33d','Otro':'#8a8494'};
const CLASSES = ['Lossless','Con pérdida','Ambiguo','Otro'];
const FMTS = topN(countBy(R,o=>o.fmt),999);
const FC = new Map(FMTS.map((e,i)=>[e[0],PAL[i%PAL.length]]));
const PERIODS = [{n:'Hasta 1969',lo:null,hi:1969},{n:'1970–1989',lo:1970,hi:1989},{n:'1990–2009',lo:1990,hi:2009},{n:'2010 en adelante',lo:2010,hi:null}];
const perOf = y => y<=1969 ? PERIODS[0].n : y<=1989 ? PERIODS[1].n : y<=2009 ? PERIODS[2].n : PERIODS[3].n;

/* ---------- estado y filtros ---------- */
const S = {yMin:null,yMax:null,bMin:null,bMax:null,artists:new Set(),albums:new Set(),genres:new Set(),fmts:new Set(),comp:'all',play:'all',norm:false,metric:'songs'};
const gkey = o => S.norm ? o.genN : o.genre;
const glabel = k => S.norm ? (GNAME.get(k)||k) : k;
let F = R;

function filtered(){ return !!(S.yMin!=null||S.yMax!=null||S.bMin!=null||S.bMax!=null||S.artists.size||S.albums.size||S.genres.size||S.fmts.size||S.comp!=='all'||S.play!=='all'); }
function passes(o){
  if(S.yMin!=null && (o.yr==null || o.yr<S.yMin)) return false;
  if(S.yMax!=null && (o.yr==null || o.yr>S.yMax)) return false;
  if(S.bMin!=null && o.br<S.bMin) return false;
  if(S.bMax!=null && o.br>S.bMax) return false;
  if(S.artists.size && !S.artists.has(o.artist)) return false;
  if(S.albums.size && !S.albums.has(o.alabel)) return false;
  if(S.genres.size && !S.genres.has(gkey(o))) return false;
  if(S.fmts.size && !S.fmts.has(o.fmt)) return false;
  if(S.comp==='complete' && !o.complete) return false;
  if(S.comp==='incomplete' && o.complete) return false;
  if(S.comp==='nogenre' && o.genre) return false;
  if(S.comp==='noyear' && o.yr!=null) return false;
  if(S.play==='never' && o.plays>0) return false;
  if(S.play==='played' && o.plays===0) return false;
  return true;
}

/* ---------- helpers de gráficos ---------- */
const GRID = 'rgba(236,230,220,.09)';
function lay(x){
  x = x||{};
  const ax = o => Object.assign({gridcolor:GRID,zerolinecolor:GRID,linecolor:GRID,automargin:true,tickfont:{size:11}},o||{});
  const base = {paper_bgcolor:'rgba(0,0,0,0)',plot_bgcolor:'rgba(0,0,0,0)',
    font:{family:'system-ui,-apple-system,"Segoe UI",Roboto,sans-serif',color:'#d9d2c7',size:12},
    margin:{l:40,r:12,t:6,b:36},colorway:PAL,showlegend:false,bargap:.18,
    hoverlabel:{bgcolor:'#2b2536',bordercolor:'#4a4259',font:{color:'#ece6dc'}},
    legend:{orientation:'h',y:-.2,font:{size:11}}};
  return Object.assign(base,x,{xaxis:ax(x.xaxis),yaxis:ax(x.yaxis)});
}
function show(id,traces,extra,click){
  const el=$(id);
  const empty = !traces.length || traces.every(t=>{ const d=t.values||t.x||t.y||t.z||[]; return !d.length; });
  if(empty){
    if(el.data) Plotly.purge(el);
    el._b=false; el.innerHTML='<div class="empty">Sin datos con los filtros actuales</div>'; el.dataset.e='1';
    return;
  }
  if(el.dataset.e==='1'){ el.innerHTML=''; el.dataset.e='0'; }
  Plotly.react(el,traces,lay(extra),{displayModeBar:false,responsive:true}).then(()=>{
    el._cf = click||null;
    if(!el._b){ el.on('plotly_click',ev=>{ if(el._cf && ev.points && ev.points[0]) el._cf(ev.points[0]); }); el._b=true; }
  });
}
function hbar(id,entries,o){
  o=o||{};
  const el=$(id), n=entries.length;
  el.style.height=Math.max(150,n*26+36)+'px';
  const idx=entries.map((_,i)=>i), mx=Math.max(1,...entries.map(e=>e[1]));
  show(id,[{type:'bar',orientation:'h',y:idx,x:entries.map(e=>e[1]),
    customdata:entries.map(e=>e.length>2?e[2]:e[0]),hovertext:entries.map(e=>String(e[0])),
    text:entries.map(e=>o.fmt?o.fmt(e[1]):fi(e[1])),textposition:'outside',cliponaxis:false,
    marker:{color:o.color||PAL[0]},hovertemplate:'%{hovertext}<br>%{text}<extra></extra>'}],
    {margin:{l:8,r:16,t:4,b:28},yaxis:{tickvals:idx,ticktext:entries.map(e=>trunc(String(e[0]),o.max||40)),autorange:'reversed'},xaxis:{range:[0,mx*1.2]}},
    o.click ? p=>o.click(p.customdata) : null);
}
function vbar(id,labels,vals,o){
  o=o||{};
  const mx=Math.max(0,...vals);
  show(id,[{type:'bar',x:labels,y:vals,customdata:o.keys||labels,text:o.text||vals.map(v=>fi(v)),textposition:'outside',cliponaxis:false,
    marker:{color:o.colors||PAL[0]},hovertemplate:(o.ht||'%{x}: %{y}')+'<extra></extra>'}],
    {yaxis:{range:[0,(mx*1.22)||1],title:o.yt?{text:o.yt}:undefined},xaxis:{type:'category'},margin:{l:48,r:8,t:16,b:40}},
    o.click ? p=>o.click(p.customdata) : null);
}
function pie(id,labels,vals,colors,click){
  show(id,[{type:'pie',labels,values:vals,hole:.55,sort:false,marker:{colors},textinfo:'percent',textfont:{color:'#15121a',size:12},
    hovertemplate:'%{label}: %{value} (%{percent})<extra></extra>'}],
    {showlegend:true,legend:{orientation:'v',x:1.02,y:.5,font:{size:11}},margin:{l:6,r:6,t:6,b:6}},
    click ? p=>click(p.label) : null);
}

/* ---------- tablas (orden, búsqueda, paginado) ---------- */
const TS = {};
function tinit(id){
  const el=$(id), st=TS[id];
  el.innerHTML='<div class="tbar"><input type="search" placeholder="Buscar en esta tabla" aria-label="Buscar en esta tabla"><span class="tcount"></span></div><div class="twrap"><table><thead></thead><tbody></tbody></table></div><div class="tpager"><button type="button" data-t="prev">Anterior</button><span></span><button type="button" data-t="next">Siguiente</button></div>';
  el.querySelector('input').addEventListener('input',e=>{ st.q=e.target.value.toLowerCase(); st.p=0; tdraw(id); });
  el.addEventListener('click',e=>{
    const th=e.target.closest('th[data-k]');
    if(th){ if(st.k===th.dataset.k) st.d=-st.d; else { st.k=th.dataset.k; st.d=th.dataset.num==='1'?-1:1; } st.p=0; tdraw(id); return; }
    const b=e.target.closest('button[data-t]');
    if(b){ st.p += b.dataset.t==='next'?1:-1; tdraw(id); }
  });
}
function table(id,cols,rows,o){
  o=o||{};
  let st=TS[id];
  if(!st){ st=TS[id]={k:o.sort?o.sort[0]:null,d:o.sort?o.sort[1]:1,p:0,q:'',size:o.size||10}; tinit(id); }
  st.cols=cols; st.rows=rows; st.p=0;
  $(id).querySelector('.tbar').style.display = o.search===false ? 'none' : '';
  tdraw(id);
}
function tdraw(id){
  const st=TS[id], el=$(id), cols=st.cols, val=(c,r)=>c.v?c.v(r):r[c.k];
  let rows=st.rows;
  if(st.q) rows=rows.filter(r=>cols.some(c=>String(val(c,r)==null?'':val(c,r)).toLowerCase().includes(st.q)));
  const sc=cols.find(c=>c.k===st.k);
  if(sc){ rows=rows.slice().sort((x,y)=>{ const a=val(sc,x), b=val(sc,y); return st.d*(typeof a==='number'&&typeof b==='number' ? a-b : String(a).localeCompare(String(b),'es')); }); }
  const pages=Math.max(1,Math.ceil(rows.length/st.size));
  st.p=Math.max(0,Math.min(st.p,pages-1));
  const slice=rows.slice(st.p*st.size,(st.p+1)*st.size);
  el.querySelector('thead').innerHTML='<tr>'+cols.map(c=>'<th data-k="'+c.k+'" data-num="'+(c.num?1:0)+'" class="'+(c.num?'n':'')+(st.k===c.k?' s':'')+'">'+esc(c.h)+(st.k===c.k?(st.d>0?' ▲':' ▼'):'')+'</th>').join('')+'</tr>';
  el.querySelector('tbody').innerHTML = slice.length
    ? slice.map(r=>'<tr>'+cols.map(c=>'<td class="'+(c.num?'n':'')+'">'+(c.f?c.f(r):esc(r[c.k]))+'</td>').join('')+'</tr>').join('')
    : '<tr><td colspan="'+cols.length+'" class="dim">Sin filas con los filtros actuales</td></tr>';
  el.querySelector('.tcount').textContent = fi(rows.length)+' filas'+(st.q?' (de '+fi(st.rows.length)+')':'');
  const pg=el.querySelector('.tpager'), btn=pg.querySelectorAll('button');
  pg.style.display = pages>1 ? '' : 'none';
  pg.querySelector('span').textContent='Página '+(st.p+1)+' de '+pages;
  btn[0].disabled=st.p===0; btn[1].disabled=st.p>=pages-1;
}

/* ---------- estructura de secciones ---------- */
const SEG = '<div class="seg" id="seg"><button type="button" data-m="songs" aria-pressed="true">Canciones</button><button type="button" data-m="albums" aria-pressed="false">Álbumes</button></div>';
const SECTIONS = [
 {id:'tiempo',t:'Distribución temporal',d:'Cuándo se publicó la música de la biblioteca, según el campo year. Tocá una barra para filtrar por ese año o década.',head:SEG,cards:[
   ['chart','cYear','Canciones por año',2,320],['chart','cDec','Por década',1,320],
   ['chart','cPer','Grandes períodos',1,300],['html','cTop','Décadas con mayor presencia',1],['html','cNoYear','Canciones sin año',1]]},
 {id:'musica',t:'Distribución musical',d:'Géneros, artistas y álbumes. Los géneros se muestran como están escritos en los metadatos.',cards:[
   ['chart','cGenreTop','15 géneros más frecuentes',2,440],['chart','cGenrePie','Distribución porcentual de géneros',1,440],
   ['chart','cArtists','20 artistas con más canciones',1,300],['chart','cAlbums','20 álbumes con más canciones',1,300],['chart','cArtDist','Cuántos artistas tienen cuántas canciones',1,300],
   ['chart','cHeat','Géneros por década',3,400],['table','tVar','Variantes de escritura de un mismo género',3]]},
 {id:'plays',t:'Reproducciones y actividad',d:'Lo que realmente se escucha, y cómo creció la biblioteca. <span id="playsNote"></span>',cards:[
   ['chart','cTopSongs','20 canciones más reproducidas',1,300],['chart','cTopArtists','15 artistas más reproducidos',1,300],['chart','cPlayGenre','Reproducciones por género',1,300],
   ['chart','cPlayDist','Canciones según veces reproducidas',1,280],['chart','cNeverAlb','Álbumes con más canciones sin reproducir',1,300],['chart','cRating','Valoraciones',1,280],
   ['chart','cLast','Última reproducción por mes',3,280],['chart','cGrow','Crecimiento de la biblioteca',3,300]]},
 {id:'formatos',t:'Formatos y calidad de audio',d:'Un bitrate alto no implica mejor calidad; por eso se separan los formatos lossless de los que pierden información.',cards:[
   ['chart','cFmtPie','Formatos',1,300],['chart','cFmtCount','Canciones por formato',1,300],['chart','cFmtSize','Espacio por formato',1,300],
   ['chart','cBrHist','Distribución de bitrate',2,300],['chart','cBrRange','Rangos de bitrate',1,300],
   ['chart','cBrAvg','Bitrate por formato',1,280],['chart','cSizeAvg','Tamaño medio de archivo por formato',1,280],['chart','cRes','Resolución de los archivos lossless',1,280],
   ['html','cCmp','Lossless frente a formatos con pérdida',3]]},
 {id:'metadatos',t:'Calidad y completitud de los metadatos',d:'Qué falta y dónde. Solo se marca lo vacío; nada se da por erróneo por ser poco común.',cards:[
   ['html','cFields','Completitud por campo',2],['html','cInd','Indicadores de catalogación',1],
   ['chart','cNoGenAlb','Álbumes con más canciones sin género',1,320],['table','tPend','Canciones pendientes de catalogación',2],
   ['table','tDup','Registros potencialmente duplicados',3]]},
 {id:'coleccion',t:'Análisis de la colección',d:'Duraciones, tamaños y relaciones entre ellos.',cards:[
   ['chart','cVar','Artistas con más años distintos',1,300],['chart','cLongAlb','Álbumes más extensos',1,300],['chart','cDurHist','Duración de las canciones',1,300],
   ['chart','cSizeHist','Tamaño de archivo',1,300],['chart','cScatter','Duración, tamaño y bitrate',2,300],
   ['table','tLong','Canciones más largas',1],['table','tShort','Canciones más cortas',1],['table','tBig','Archivos más pesados',1],
   ['table','tAll','Explorador de canciones',3]]}
];
function card(c){
  const type=c[0], id=c[1], t=c[2], w=c[3]||1, h=c[4]||300;
  const body = type==='chart' ? '<div id="'+id+'" class="chart" style="height:'+h+'px"></div>' : '<div id="'+id+'"></div>';
  return '<article class="card w'+w+'"><h3 id="'+id+'-t">'+t+'</h3><p class="sub" id="'+id+'-sub"></p>'+body+'</article>';
}
$('sections').innerHTML = SECTIONS.map(s=>'<section id="'+s.id+'"><div class="shead"><div><h2>'+s.t+'</h2><p id="'+s.id+'-d">'+s.d+'</p></div>'+(s.head||'')+'</div><div class="grid">'+s.cards.map(card).join('')+'</div></section>').join('');

/* ---------- acciones de filtro ---------- */
const CH = {artists:'chArtists',albums:'chAlbums',genres:'chGenres'};
const OPT = {artists:new Map(),albums:new Map(),genres:new Map()};
let timer=null;
function sched(){ clearTimeout(timer); timer=setTimeout(update,120); }
function drawChips(set){
  const box=$(CH[set]); box.textContent='';
  for(const v of S[set]){
    const b=document.createElement('button');
    b.type='button'; b.className='chip'; b.dataset.set=set; b.dataset.v=v; b.title='Quitar este filtro';
    b.textContent=(set==='genres'?glabel(v):v)+' ×';
    box.appendChild(b);
  }
}
function addTo(set,val){ if(val==null||val==='') return; S[set].add(val); drawChips(set); sched(); }
function syncFmts(){ document.querySelectorAll('#fmts .chip').forEach(b=>b.setAttribute('aria-pressed',S.fmts.has(b.dataset.f)?'true':'false')); }
function addFmt(f){ if(S.fmts.has(f)) S.fmts.delete(f); else S.fmts.add(f); syncFmts(); sched(); }
function setYears(a,b){ S.yMin=a; S.yMax=b; $('yMin').value=a==null?'':a; $('yMax').value=b==null?'':b; sched(); }

function fillList(set,dlId){
  const dl=$(dlId); dl.textContent='';
  const fr=document.createDocumentFragment();
  for(const l of OPT[set].keys()){ const o=document.createElement('option'); o.value=l; fr.appendChild(o); }
  dl.appendChild(fr);
}
function buildOpts(){
  const coll=(a,b)=>a.localeCompare(b,'es');
  OPT.artists=new Map([...new Set(R.map(o=>o.artist).filter(Boolean))].sort(coll).map(a=>[a,a]));
  OPT.albums=new Map([...new Set([...AL.values()].map(a=>a.label))].sort(coll).map(a=>[a,a]));
  buildGenreOpts();
  fillList('artists','dlArtists'); fillList('albums','dlAlbums');
}
function buildGenreOpts(){
  const keys=[...new Set(R.map(o=>gkey(o)).filter(Boolean))];
  OPT.genres=new Map(keys.map(k=>[glabel(k),k]).sort((a,b)=>a[0].localeCompare(b[0],'es')));
  fillList('genres','dlGenres');
}
function wirePicker(set,inId){
  const inp=$(inId);
  const tryAdd=()=>{ const v=inp.value; if(OPT[set].has(v)){ inp.value=''; addTo(set,OPT[set].get(v)); } };
  inp.addEventListener('change',tryAdd);
  inp.addEventListener('input',e=>{ if(!e.inputType || e.inputType==='insertReplacementText') tryAdd(); });
}
function numInput(id,key){ $(id).addEventListener('input',e=>{ const v=e.target.value; S[key]=v===''?null:+v; sched(); }); }

function initFilters(){
  buildOpts();
  wirePicker('artists','inArtists'); wirePicker('albums','inAlbums'); wirePicker('genres','inGenres');
  numInput('yMin','yMin'); numInput('yMax','yMax'); numInput('bMin','bMin'); numInput('bMax','bMax');
  $('fmts').innerHTML=FMTS.map(e=>'<button type="button" class="chip" data-f="'+esc(e[0])+'" aria-pressed="false">'+esc(e[0])+' <small>'+fi(e[1])+'</small></button>').join('');
  $('fmts').addEventListener('click',e=>{ const b=e.target.closest('.chip[data-f]'); if(b) addFmt(b.dataset.f); });
  $('filters').addEventListener('click',e=>{
    const c=e.target.closest('.chip[data-set]');
    if(c){ S[c.dataset.set].delete(c.dataset.v); drawChips(c.dataset.set); sched(); }
  });
  $('sComp').addEventListener('change',e=>{ S.comp=e.target.value; sched(); });
  $('sPlay').addEventListener('change',e=>{ S.play=e.target.value; sched(); });
  $('cNorm').addEventListener('change',e=>{ S.norm=e.target.checked; S.genres.clear(); drawChips('genres'); buildGenreOpts(); sched(); });
  $('clear').addEventListener('click',()=>{
    Object.assign(S,{yMin:null,yMax:null,bMin:null,bMax:null,comp:'all',play:'all'});
    S.artists.clear(); S.albums.clear(); S.genres.clear(); S.fmts.clear();
    ['yMin','yMax','bMin','bMax','inArtists','inAlbums','inGenres'].forEach(i=>$(i).value='');
    $('sComp').value='all'; $('sPlay').value='all';
    Object.keys(CH).forEach(drawChips); syncFmts(); sched();
  });
  $('seg').addEventListener('click',e=>{
    const b=e.target.closest('button[data-m]'); if(!b) return;
    S.metric=b.dataset.m;
    $('seg').querySelectorAll('button').forEach(x=>x.setAttribute('aria-pressed',x===b?'true':'false'));
    renderTime();
  });
  document.addEventListener('click',e=>{
    const a=e.target.closest('[data-act]'); if(!a) return;
    if(a.dataset.act==='noyear'){ S.comp='noyear'; $('sComp').value='noyear'; sched(); }
  });
  if(window.innerWidth<800) $('filters').open=false;
}

/* ---------- render: resumen ---------- */
function renderKpis(){
  const n=F.length, secs=sum(F,o=>o.dur), bytes=sum(F,o=>o.sz);
  const d=Math.floor(secs/86400), h=Math.floor((secs%86400)/3600), m=Math.floor((secs%3600)/60);
  $('kDur').innerHTML='<span>'+fi(d)+'</span> días <span>'+h+'</span> h <span>'+m+'</span> min';
  setText('kDurSub',fi(secs/3600)+' horas de música continua en '+fi(n)+' canciones');
  setText('kSize',f1(bytes/1e9)+' GB');
  setText('kSizeSub',n ? f1(bytes/n/1e6)+' MB por canción en promedio' : '');
  const art=new Set(), alb=new Set();
  let yMin=Infinity,yMax=-Infinity,wg=0,wy=0,cm=0,pl=0,tp=0,st=0;
  for(const o of F){
    if(o.artist) art.add(o.artist); if(o.akey) alb.add(o.akey);
    if(o.yr!=null){ wy++; if(o.yr<yMin) yMin=o.yr; if(o.yr>yMax) yMax=o.yr; }
    if(o.genre) wg++; if(o.complete) cm++; if(o.plays>0) pl++; tp+=o.plays; if(o.starred) st++;
  }
  const K=[
    ['Canciones',fi(n),'registros'+(filtered()?', de '+fi(R.length)+' en la biblioteca':' del inventario')],
    ['Artistas',fi(art.size),'valores distintos del campo artist'],
    ['Álbumes',fi(alb.size),'álbumes únicos, no filas'],
    ['Año más antiguo y más reciente',wy?yMin+' a '+yMax:'sin datos',frac(wy,n)+' tienen año'],
    ['Con género',pcs(wg,n),frac(wg,n)],
    ['Metadatos completos',pcs(cm,n),frac(cm,n)+' con los 9 campos'],
    ['Reproducciones',fi(tp),pcs(pl,n)+' reproducidas al menos una vez ('+frac(pl,n)+')'],
    ['Favoritas',fi(st),'canciones con estrella']
  ];
  $('kpis').innerHTML=K.map(k=>'<div class="kpi"><div class="l">'+k[0]+'</div><div class="v">'+k[1]+'</div><div class="s">'+esc(k[2])+'</div></div>').join('');
  setText('count',fi(n)+' de '+fi(R.length)+' canciones');
}

/* ---------- render: tiempo ---------- */
function renderTime(){
  const M=S.metric, unit=M==='songs'?'canciones':'álbumes', cap=M==='songs'?'Canciones':'Álbumes';
  const wy=F.filter(o=>o.yr!=null);
  const by=kf=>{
    const m=new Map();
    if(M==='songs'){ for(const o of wy){ const k=kf(o); m.set(k,(m.get(k)||0)+1); } }
    else{
      const s=new Map();
      for(const o of wy){ if(!o.akey) continue; const k=kf(o); let t=s.get(k); if(!t){ t=new Set(); s.set(k,t); } t.add(o.akey); }
      for(const [k,t] of s) m.set(k,t.size);
    }
    return m;
  };
  setText('cYear-t',cap+' por año'); setText('cDec-t',cap+' por década'); setText('cPer-t','Grandes períodos ('+unit+')');
  const note = M==='songs'
    ? frac(wy.length,F.length)+' tienen año'
    : fi(new Set(wy.filter(o=>o.akey).map(o=>o.akey)).size)+' álbumes con canciones fechadas; si un álbum tiene años distintos, cuenta en cada uno';
  ['cYear','cDec','cPer'].forEach(i=>setSub(i,note));
  const ym=by(o=>o.yr), ys=[...ym.keys()].sort((a,b)=>a-b);
  show('cYear',[{type:'bar',x:ys,y:ys.map(k=>ym.get(k)),marker:{color:PAL[0]},hovertemplate:'%{x}: %{y} '+unit+'<extra></extra>'}],
    {xaxis:{type:'linear'},margin:{l:44,r:8,t:6,b:34}},p=>setYears(p.x,p.x));
  const dm=by(o=>o.dec), ds=[...dm.keys()].sort((a,b)=>a-b);
  vbar('cDec',ds.map(d=>d+'s'),ds.map(d=>dm.get(d)),{keys:ds,click:k=>setYears(k,k+9),ht:'%{x}: %{y} '+unit});
  const pm=by(o=>perOf(o.yr)), pe=PERIODS.filter(p=>pm.get(p.n));
  pie('cPer',pe.map(p=>p.n),pe.map(p=>pm.get(p.n)),pe.map((p,i)=>PAL[i]),l=>{ const p=PERIODS.find(x=>x.n===l); if(p) setYears(p.lo,p.hi); });
  setSub('cTop','porcentaje sobre '+fi([...dm.values()].reduce((a,b)=>a+b,0))+' '+unit+' con año');
  const tot=[...dm.values()].reduce((a,b)=>a+b,0), top=topN(dm,3);
  $('cTop').innerHTML = top.length
    ? '<ol class="rank">'+top.map(e=>'<li><strong>'+e[0]+'s</strong><span>'+fi(e[1])+' '+unit+' · '+pcs(e[1],tot)+'</span></li>').join('')+'</ol>'
    : '<div class="empty">Sin datos con los filtros actuales</div>';
  const noY=F.length-wy.length;
  setSub('cNoYear',frac(noY,F.length)+' sin año');
  $('cNoYear').innerHTML='<div class="stat">'+fi(noY)+'</div><p class="dim">'+pcs(noY,F.length)+' de '+fi(F.length)+' canciones</p>'+(noY?'<button class="btn" type="button" data-act="noyear">Ver solo esas canciones</button>':'');
}

/* ---------- render: música ---------- */
function renderMusic(){
  const wg=F.filter(o=>o.genre), gm=countBy(wg,gkey), g15=topN(gm,15);
  setSub('cGenreTop',frac(wg.length,F.length)+' tienen género · '+fi(gm.size)+' géneros distintos'+(S.norm?' (normalizados)':' (tal como están en los metadatos)'));
  hbar('cGenreTop',g15.map(([k,v])=>[glabel(k),v,k]),{color:PAL[2],click:k=>addTo('genres',k)});
  const t10=topN(gm,10), rest=wg.length-sum(t10,e=>e[1]);
  const lab=t10.map(e=>glabel(e[0])), val=t10.map(e=>e[1]);
  if(rest>0){ lab.push('Otros'); val.push(rest); }
  setSub('cGenrePie','porcentaje sobre '+frac(wg.length,F.length)+' con género');
  pie('cGenrePie',lab,val,lab.map((_,i)=>i<10?PAL[i%PAL.length]:'#5b5568'),l=>{ const e=t10.find(x=>glabel(x[0])===l); if(e) addTo('genres',e[0]); });

  const am=countBy(F,o=>o.artist);
  setSub('cArtists',fi(am.size)+' artistas · '+frac(F.filter(o=>o.artist).length,F.length)+' con artista');
  hbar('cArtists',topN(am,20),{color:PAL[1],click:a=>addTo('artists',a)});
  const lm=countBy(F,o=>o.akey);
  setSub('cAlbums',fi(lm.size)+' álbumes · '+frac(F.filter(o=>o.akey).length,F.length)+' con álbum');
  hbar('cAlbums',topN(lm,20).map(([k,v])=>[AL.get(k).label,v]),{color:PAL[4],click:l=>addTo('albums',l)});

  const B=[['1',1,1],['2',2,2],['3 a 5',3,5],['6 a 10',6,10],['11 a 20',11,20],['21 a 50',21,50],['más de 50',51,1e9]];
  const bc=B.map(b=>{ let c=0; for(const v of am.values()) if(v>=b[1]&&v<=b[2]) c++; return c; });
  setSub('cArtDist',fi(am.size)+' artistas agrupados por su cantidad de canciones');
  vbar('cArtDist',B.map(b=>b[0]),bc,{colors:PAL[3],yt:'artistas',ht:'%{x} canciones: %{y} artistas'});

  const gd=wg.filter(o=>o.dec!=null), gset=g15.map(e=>e[0]);
  const dset=[...new Set(gd.map(o=>o.dec))].sort((a,b)=>a-b);
  const cell=new Map();
  for(const o of gd){ const k=gkey(o)+'\u0001'+o.dec; cell.set(k,(cell.get(k)||0)+1); }
  const z=gset.map(g=>dset.map(d=>cell.get(g+'\u0001'+d)||null));
  $('cHeat').style.height=Math.max(200,gset.length*26+80)+'px';
  setSub('cHeat',frac(gd.length,F.length)+' tienen género y año · los 15 géneros más frecuentes');
  show('cHeat',gset.length&&dset.length?[{type:'heatmap',z,x:dset.map(d=>d+'s'),y:gset.map(glabel),xgap:2,ygap:2,
    colorscale:[[0,'#2f2839'],[.5,'#9a6a3a'],[1,'#e8a33d']],colorbar:{thickness:10,len:.9},
    hovertemplate:'%{y} en %{x}: %{z} canciones<extra></extra>'}]:[],
    {yaxis:{type:'category',autorange:'reversed'},xaxis:{type:'category'},margin:{l:8,r:8,t:6,b:30}});

  const vm=new Map();
  for(const o of wg){ let m=vm.get(o.genN); if(!m){ m=new Map(); vm.set(o.genN,m); } m.set(o.genre,(m.get(o.genre)||0)+1); }
  const vr=[...vm.entries()].filter(e=>e[1].size>1).map(([k,m])=>({
    g:GNAME.get(k), nv:m.size, n:sum([...m.values()],x=>x),
    v:[...m.entries()].sort((a,b)=>b[1]-a[1]).map(([name,c])=>name+' ('+fi(c)+')').join('; ')}));
  setSub('tVar',fi(vr.length)+' géneros se escriben de más de una forma. Es solo una vista de estudio: los datos originales no se tocan.');
  table('tVar',[{k:'g',h:'Género normalizado'},{k:'nv',h:'Formas',num:true},{k:'v',h:'Variantes encontradas (canciones)'},{k:'n',h:'Canciones',num:true,f:r=>fi(r.n)}],vr,{sort:['n',-1],size:8});
}

/* ---------- render: reproducciones ---------- */
function renderPlays(){
  setText('playsNote', R.some(o=>o.plays>0) ? '' : 'Navidrome no devolvió reproducciones para este usuario.');
  const played=F.filter(o=>o.plays>0);
  setSub('cTopSongs',frac(played.length,F.length)+' reproducidas al menos una vez');
  hbar('cTopSongs',played.slice().sort((a,b)=>b.plays-a.plays).slice(0,20).map(o=>[(o.title||'(sin título)')+' ('+(o.artist||'sin artista')+')',o.plays]),{color:PAL[0]});

  const pa=new Map(); for(const o of played){ if(o.artist) pa.set(o.artist,(pa.get(o.artist)||0)+o.plays); }
  setSub('cTopArtists','suma de reproducciones de sus canciones');
  hbar('cTopArtists',topN(pa,15),{color:PAL[1],click:a=>addTo('artists',a)});

  const pg=new Map(); for(const o of played){ const k=gkey(o); if(k) pg.set(k,(pg.get(k)||0)+o.plays); }
  setSub('cPlayGenre','reproducciones de canciones con género');
  hbar('cPlayGenre',topN(pg,12).map(([k,v])=>[glabel(k),v,k]),{color:PAL[2],click:k=>addTo('genres',k)});

  const B=[['0',0,0],['1',1,1],['2 a 5',2,5],['6 a 10',6,10],['11 a 25',11,25],['más de 25',26,1e9]];
  setSub('cPlayDist','sobre '+fi(F.length)+' canciones');
  vbar('cPlayDist',B.map(b=>b[0]),B.map(b=>F.filter(o=>o.plays>=b[1]&&o.plays<=b[2]).length),{colors:PAL[4],yt:'canciones',ht:'%{x} reproducciones: %{y} canciones'});

  const nm=new Map(); for(const o of F){ if(o.akey && o.plays===0) nm.set(o.akey,(nm.get(o.akey)||0)+1); }
  setSub('cNeverAlb',frac(F.filter(o=>o.plays===0).length,F.length)+' sin reproducir');
  hbar('cNeverAlb',topN(nm,15).map(([k,v])=>[AL.get(k).label,v]),{color:PAL[3],click:l=>addTo('albums',l)});

  const rt=[1,2,3,4,5].map(r=>F.filter(o=>o.rating===r).length), st=F.filter(o=>o.starred).length;
  setSub('cRating','favoritas: '+frac(st,F.length)+' · valoradas: '+frac(sum(rt,x=>x),F.length));
  if(rt.every(v=>!v)) vbar('cRating',[],[],{}); else vbar('cRating',['1','2','3','4','5'],rt,{colors:PAL[0],yt:'canciones',ht:'%{x} estrellas: %{y}'});

  const lp=F.filter(o=>o.played), lm=countBy(lp,o=>mkey(o.played)), lk=[...lm.keys()].sort();
  setSub('cLast',frac(lp.length,F.length)+' con fecha de última reproducción; cada canción cuenta solo en el mes de su última escucha');
  show('cLast',[{type:'bar',x:lk,y:lk.map(k=>lm.get(k)),marker:{color:PAL[1]},hovertemplate:'%{x}: %{y} canciones<extra></extra>'}],{yaxis:{title:{text:'canciones'}},margin:{l:48,r:8,t:6,b:34}});

  const cr=F.filter(o=>o.created), cm=countBy(cr,o=>mkey(o.created)), ck=[...cm.keys()].sort();
  let acc=0; const cum=ck.map(k=>acc+=cm.get(k));
  setSub('cGrow',frac(cr.length,F.length)+' con fecha de alta (cuando Navidrome indexó el archivo, no cuando se compró)');
  show('cGrow',[{type:'bar',x:ck,y:ck.map(k=>cm.get(k)),name:'Altas del mes',marker:{color:PAL[1]},opacity:.8},
    {type:'scatter',mode:'lines',x:ck,y:cum,name:'Acumulado',yaxis:'y2',line:{color:PAL[0],width:2.5}}],
    {showlegend:true,yaxis:{title:{text:'altas'}},yaxis2:{overlaying:'y',side:'right',showgrid:false,title:{text:'acumulado'},automargin:true},margin:{l:48,r:48,t:6,b:48}});
}

/* ---------- render: formatos ---------- */
function renderFormats(){
  const fl=topN(countBy(F,o=>o.fmt),999), names=fl.map(e=>e[0]), col=names.map(f=>FC.get(f));
  setSub('cFmtPie','porcentaje sobre '+fi(F.length)+' canciones');
  pie('cFmtPie',names,fl.map(e=>e[1]),col,l=>addFmt(l));
  setSub('cFmtCount','cantidad y porcentaje sobre '+fi(F.length)+' canciones');
  vbar('cFmtCount',names,fl.map(e=>e[1]),{colors:col,click:l=>addFmt(l),text:fl.map(e=>fi(e[1])+' ('+pcs(e[1],F.length)+')')});

  const szm=new Map(); for(const o of F) szm.set(o.fmt,(szm.get(o.fmt)||0)+o.sz);
  const total=sum(F,o=>o.sz);
  setSub('cFmtSize','sobre '+f1(total/1e9)+' GB en total');
  vbar('cFmtSize',names,names.map(n=>szm.get(n)/1e9),{colors:col,yt:'GB',ht:'%{x}: %{y:.1f} GB',text:names.map(n=>f1(szm.get(n)/1e9)+' GB ('+pcs(szm.get(n),total)+')')});

  const wb=F.filter(o=>o.br>0);
  setSub('cBrHist',frac(wb.length,F.length)+' con bitrate · tramos de 16 kbps, coloreado por tipo de formato');
  show('cBrHist',CLASSES.map(c=>({type:'histogram',name:c,x:wb.filter(o=>o.cls===c).map(o=>o.br),xbins:{size:16},marker:{color:CLSCOL[c]},hovertemplate:'%{x} kbps: %{y}<extra>'+c+'</extra>'})).filter(t=>t.x.length),
    {barmode:'stack',showlegend:true,xaxis:{title:{text:'kbps'}},yaxis:{title:{text:'canciones'}},margin:{l:48,r:8,t:6,b:50}});

  const BR=[['< 128',0,127],['128 a 159',128,159],['160 a 191',160,191],['192 a 223',192,223],['224 a 255',224,255],['256 a 319',256,319],['320',320,320],['321 a 639',321,639],['640 o más',640,1e9]];
  setSub('cBrRange',frac(wb.length,F.length)+' con bitrate');
  show('cBrRange',CLASSES.map(c=>({type:'bar',name:c,x:BR.map(b=>b[0]),y:BR.map(b=>wb.filter(o=>o.cls===c&&o.br>=b[1]&&o.br<=b[2]).length),marker:{color:CLSCOL[c]},hovertemplate:'%{x} kbps: %{y}<extra>'+c+'</extra>'})).filter(t=>t.y.some(v=>v)),
    {barmode:'stack',showlegend:true,xaxis:{type:'category'},yaxis:{title:{text:'canciones'}},margin:{l:48,r:8,t:6,b:50}});

  const brm=new Map(); for(const o of wb){ let a=brm.get(o.fmt); if(!a){ a=[]; brm.set(o.fmt,a); } a.push(o.br); }
  const bn=names.filter(n=>brm.has(n));
  setSub('cBrAvg','con VBR el promedio engaña; la mediana describe mejor');
  show('cBrAvg',[{type:'bar',name:'Promedio',x:bn,y:bn.map(n=>Math.round(mean(brm.get(n)))),marker:{color:PAL[0]},hovertemplate:'%{x}: %{y} kbps<extra>promedio</extra>'},
    {type:'bar',name:'Mediana',x:bn,y:bn.map(n=>Math.round(median(brm.get(n)))),marker:{color:PAL[2]},hovertemplate:'%{x}: %{y} kbps<extra>mediana</extra>'}],
    {barmode:'group',showlegend:true,xaxis:{type:'category'},yaxis:{title:{text:'kbps'}},margin:{l:48,r:8,t:6,b:50}});

  const szA=new Map(); for(const o of F){ if(o.sz>0){ let a=szA.get(o.fmt); if(!a){ a=[]; szA.set(o.fmt,a); } a.push(o.sz/1e6); } }
  const sn=names.filter(n=>szA.has(n));
  setSub('cSizeAvg','promedio por archivo, en MB');
  vbar('cSizeAvg',sn,sn.map(n=>mean(szA.get(n))),{colors:sn.map(n=>FC.get(n)),yt:'MB',ht:'%{x}: %{y:.1f} MB',text:sn.map(n=>f1(mean(szA.get(n)))+' MB')});

  const rm=new Map(); for(const o of F){ if(o.cls==='Lossless'&&o.bd>0&&o.sr>0){ const k=o.bd+' bit / '+f1(o.sr/1000)+' kHz'; rm.set(k,(rm.get(k)||0)+1); } }
  setSub('cRes','solo archivos lossless con profundidad y frecuencia informadas');
  hbar('cRes',topN(rm,10),{color:PAL[1]});

  const rows=CLASSES.map(c=>{
    const a=F.filter(o=>o.cls===c); if(!a.length) return null;
    const by2=sum(a,o=>o.sz), du=sum(a,o=>o.dur);
    return {c,fm:[...new Set(a.map(o=>o.fmt))].sort().join(', '),n:a.length,by:by2,du,br:median(a.filter(o=>o.br>0).map(o=>o.br)),avg:by2/a.length};
  }).filter(Boolean);
  setSub('cCmp','porcentajes sobre '+fi(F.length)+' canciones');
  const m4=F.filter(o=>o.cls==='Ambiguo'), hi=m4.filter(o=>o.br>=600).length;
  $('cCmp').innerHTML = rows.length
    ? '<div class="twrap"><table><thead><tr><th>Tipo</th><th>Formatos</th><th class="n">Canciones</th><th class="n">% del total</th><th class="n">Espacio</th><th class="n">Tamaño medio</th><th class="n">Bitrate mediano</th><th class="n">MB por minuto</th></tr></thead><tbody>'
      + rows.map(r=>'<tr><td><span class="mk" style="background:transparent;color:'+CLSCOL[r.c]+';padding:0">●</span> '+r.c+'</td><td>'+esc(r.fm)+'</td><td class="n">'+fi(r.n)+'</td><td class="n">'+pcs(r.n,F.length)+'</td><td class="n">'+f1(r.by/1e9)+' GB</td><td class="n">'+f1(r.avg/1e6)+' MB</td><td class="n">'+fi(r.br)+' kbps</td><td class="n">'+(r.du>0?f1(r.by/1e6/(r.du/60)):'–')+'</td></tr>').join('')
      + '</tbody></table></div><p class="note">Ambiguo reúne m4a/mp4: el contenedor puede llevar AAC (con pérdida) o ALAC (lossless) y el inventario no lo indica.'
      + (m4.length?' '+fi(hi)+' de '+fi(m4.length)+' superan los 600 kbps, lo que sugiere ALAC, pero es solo una pista.':'')+'</p>'
    : '<div class="empty">Sin datos con los filtros actuales</div>';
}

/* ---------- render: metadatos ---------- */
function renderMeta(){
  const n=F.length, ec={}; FIELDS.forEach(f=>ec[f[0]]=0);
  for(const o of F) for(const k of o.miss) ec[k]++;
  setSub('cFields','n = '+fi(n)+' canciones · vacío = sin valor o marcador [Unknown …] de Navidrome');
  $('cFields').innerHTML='<table class="ft"><thead><tr><th>Campo</th><th class="n">Completos</th><th class="n">Vacíos</th><th>Completitud</th><th class="n">%</th></tr></thead><tbody>'
    + FIELDS.map(([k,l])=>{ const ok=n-ec[k], p=pc(ok,n); return '<tr><td>'+l+'</td><td class="n">'+fi(ok)+'</td><td class="n">'+fi(ec[k])+'</td><td><div class="bar"><i style="width:'+p+'%;background:'+(p>=99.5?'var(--teal)':p>=90?'var(--amber)':'var(--rose)')+'"></i></div></td><td class="n">'+f1(p)+'%</td></tr>'; }).join('')
    + '</tbody></table>';

  const alInc=new Map(), arInc=new Map();
  for(const o of F){
    if(o.akey){ alInc.set(o.akey,(alInc.get(o.akey)||false)||o.miss.length>0); }
    if(o.artist){ arInc.set(o.artist,(arInc.get(o.artist)||false)||o.miss.length>0); }
  }
  const cntT=m=>[...m.values()].filter(Boolean).length;
  const dm=new Map();
  for(const o of F){ if(!o.title||!o.artist) continue; const k=norm(o.title)+'\u0001'+norm(o.artist)+'\u0001'+norm(o.album); let a=dm.get(k); if(!a){ a=[]; dm.set(k,a); } a.push(o); }
  const dups=[...dm.values()].filter(a=>a.length>1);
  const extra=sum(dups,a=>a.length-1);
  setSub('cInd','cada indicador con su denominador');
  $('cInd').innerHTML='<div class="ind">'
    +'<div><b>'+fi(ec.genre)+'</b>sin género<small>'+pcs(ec.genre,n)+' de '+fi(n)+' canciones</small></div>'
    +'<div><b>'+fi(ec.year)+'</b>sin año<small>'+pcs(ec.year,n)+' de '+fi(n)+' canciones</small></div>'
    +'<div><b>'+fi(cntT(alInc))+'</b>álbumes con metadatos incompletos<small>'+frac(cntT(alInc),alInc.size,'álbumes')+' · '+fi(ec.album)+' canciones sin álbum</small></div>'
    +'<div><b>'+fi(cntT(arInc))+'</b>artistas con información incompleta<small>'+frac(cntT(arInc),arInc.size,'artistas')+' · '+fi(ec.artist)+' canciones sin artista</small></div>'
    +'<div><b>'+fi(dups.length)+'</b>grupos de posibles duplicados<small>'+fi(extra)+' registros de más sobre '+fi(n)+'</small></div></div>'
    +'<p class="note">Incompleto = al menos una canción con algún campo vacío.</p>';

  const ng=new Map(); for(const o of F){ if(o.akey && !o.genre) ng.set(o.akey,(ng.get(o.akey)||0)+1); }
  setSub('cNoGenAlb',frac(ec.genre,n)+' sin género');
  hbar('cNoGenAlb',topN(ng,15).map(([k,v])=>[AL.get(k).label,v]),{color:PAL[3],click:l=>addTo('albums',l)});

  const pend=F.filter(o=>o.miss.length);
  setSub('tPend',frac(pend.length,n)+' tienen al menos un campo vacío');
  table('tPend',[
    {k:'title',h:'Title',f:o=>esc(o.title)||'<span class="dim">vacío</span>'},
    {k:'artist',h:'Artist',f:o=>esc(o.artist)||'<span class="dim">vacío</span>'},
    {k:'album',h:'Album',f:o=>esc(o.album)||'<span class="dim">vacío</span>'},
    {k:'yr',h:'Year',num:true,v:o=>o.yr||0,f:o=>o.yr||'–'},
    {k:'miss',h:'Campos incompletos',v:o=>o.miss.length,f:o=>o.miss.map(k=>'<span class="mk">'+FN[k]+'</span>').join('')}
  ],pend,{sort:['miss',-1],size:10});

  setSub('tDup','mismo título, artista y álbum (sin distinguir mayúsculas ni acentos) · son candidatos, decidís vos');
  table('tDup',[
    {k:'title',h:'Title'},{k:'artist',h:'Artist'},{k:'album',h:'Album'},
    {k:'n',h:'Copias',num:true},{k:'fm',h:'Formatos'},{k:'pl',h:'Reproducciones',num:true}
  ],dups.map(a=>({title:a[0].title,artist:a[0].artist,album:a[0].album,n:a.length,fm:[...new Set(a.map(o=>o.fmt))].join(', '),pl:sum(a,o=>o.plays)})),{sort:['n',-1],size:8});
}

/* ---------- render: colección ---------- */
function histRange(vals){ const s=vals.slice().sort((a,b)=>a-b); return s.length ? s[Math.min(s.length-1,Math.floor(.99*(s.length-1)))] : 0; }
function renderCollection(){
  const ya=new Map(); for(const o of F){ if(o.artist && o.yr!=null){ let s=ya.get(o.artist); if(!s){ s=new Set(); ya.set(o.artist,s); } s.add(o.yr); } }
  setSub('cVar','cantidad de años distintos entre sus canciones');
  hbar('cVar',topN(new Map([...ya].map(([k,s])=>[k,s.size])),15),{color:PAL[5],click:a=>addTo('artists',a)});

  const ad=new Map(); for(const o of F){ if(o.akey) ad.set(o.akey,(ad.get(o.akey)||0)+o.dur); }
  setSub('cLongAlb','duración total del álbum, en minutos');
  hbar('cLongAlb',topN(ad,15).map(([k,v])=>[AL.get(k).label,Math.round(v/60)]),{color:PAL[6],fmt:v=>fi(v)+' min',click:l=>addTo('albums',l)});

  const dv=F.filter(o=>o.dur>0).map(o=>o.dur/60), dp=histRange(dv);
  setSub('cDurHist',frac(dv.length,F.length)+' con duración · tramos de 30 s · se corta en el percentil 99');
  show('cDurHist',[{type:'histogram',x:dv,xbins:{size:.5},marker:{color:PAL[1]},hovertemplate:'%{x} min: %{y}<extra></extra>'}],
    {xaxis:{title:{text:'minutos'},range:[0,dp*1.05]},yaxis:{title:{text:'canciones'}},margin:{l:48,r:8,t:6,b:46}});

  const sv=F.filter(o=>o.sz>0).map(o=>o.sz/1e6), sp=histRange(sv), bs=Math.max(1,Math.round(sp/50));
  setSub('cSizeHist',frac(sv.length,F.length)+' con tamaño · tramos de '+bs+' MB · se corta en el percentil 99');
  show('cSizeHist',[{type:'histogram',x:sv,xbins:{size:bs},marker:{color:PAL[2]},hovertemplate:'%{x} MB: %{y}<extra></extra>'}],
    {xaxis:{title:{text:'MB'},range:[0,sp*1.05]},yaxis:{title:{text:'canciones'}},margin:{l:48,r:8,t:6,b:46}});

  const sc=F.filter(o=>o.dur>0&&o.sz>0&&o.br>0);
  setSub('cScatter',frac(sc.length,F.length)+' con duración, tamaño y bitrate · el color indica el bitrate');
  show('cScatter',[{type:'scattergl',mode:'markers',x:sc.map(o=>o.dur/60),y:sc.map(o=>o.sz/1e6),
    customdata:sc.map(o=>(o.title||'(sin título)')+' ('+(o.artist||'sin artista')+') · '+o.fmt+' · '+o.br+' kbps'),
    marker:{size:4,opacity:.65,color:sc.map(o=>o.br),colorscale:[[0,'#4a3f6b'],[.5,'#9a86e0'],[1,'#e8a33d']],colorbar:{title:{text:'kbps'},thickness:10,len:.85}},
    hovertemplate:'%{customdata}<br>%{x:.1f} min · %{y:.1f} MB<extra></extra>'}],
    {xaxis:{title:{text:'minutos'}},yaxis:{title:{text:'MB'}},margin:{l:52,r:8,t:6,b:46}});

  const wd=F.filter(o=>o.dur>0);
  const dcols=[{k:'title',h:'Title'},{k:'artist',h:'Artist'},{k:'dur',h:'Duración',num:true,f:o=>mmss(o.dur)}];
  setSub('tLong','las 10 de mayor duración'); setSub('tShort','las 10 de menor duración (excluye duración 0)');
  table('tLong',dcols,wd.slice().sort((a,b)=>b.dur-a.dur).slice(0,10),{search:false,sort:['dur',-1],size:10});
  table('tShort',dcols,wd.slice().sort((a,b)=>a.dur-b.dur).slice(0,10),{search:false,sort:['dur',1],size:10});
  setSub('tBig','los 10 archivos de mayor tamaño');
  table('tBig',[{k:'title',h:'Title'},{k:'artist',h:'Artist'},{k:'sz',h:'Tamaño',num:true,f:o=>f1(o.sz/1e6)+' MB'}],F.filter(o=>o.sz>0).sort((a,b)=>b.sz-a.sz).slice(0,10),{search:false,sort:['sz',-1],size:10});

  setSub('tAll',fi(F.length)+' canciones con los filtros actuales · clic en un encabezado para ordenar');
  table('tAll',[
    {k:'title',h:'Title'},{k:'artist',h:'Artist'},{k:'album',h:'Album'},
    {k:'yr',h:'Year',num:true,v:o=>o.yr||0,f:o=>o.yr||'–'},{k:'genre',h:'Genre'},{k:'fmt',h:'Formato'},
    {k:'br',h:'Bitrate',num:true,f:o=>o.br?o.br+' kbps':'–'},{k:'dur',h:'Duración',num:true,f:o=>mmss(o.dur)},
    {k:'sz',h:'Tamaño',num:true,f:o=>f1(o.sz/1e6)+' MB'},{k:'plays',h:'Reprod.',num:true}
  ],F,{sort:['artist',1],size:15});
}

/* ---------- ciclo ---------- */
function update(){
  F=R.filter(passes);
  renderKpis(); renderTime(); renderMusic(); renderPlays(); renderFormats(); renderMeta(); renderCollection();
}

setText('meta', fi(R.length)+' canciones leídas de Navidrome el '+new Date(RAW.generated).toLocaleString('es-ES',{dateStyle:'long',timeStyle:'short'}));
initFilters();
update();
})();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()