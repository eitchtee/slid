"""Builds slid/words.py from open word lists. Not part of the game.

    uv run --with wordfreq python scripts/build_words.py

Sources (downloaded into scripts/.words-cache/, which is gitignored):

- English: 12dicts 6.0.2 by Alan Beale (public domain; acknowledgment requested).
  3esl.txt (words in at least 3 of 6 learner's dictionaries) is the pool, and
  Lemmatized/2+2+3lem.txt keeps only headwords, so plurals and verb forms never
  get in. Ranked by frequency with wordfreq (Apache-2.0), most common first.
- Portuguese: fserb/pt-br by Fernando Serboncini, Termo's author (MIT). The
  lexicon is the pool and its ICF scores rank it. The Portuguese lists below are
  kept by hand from that ranking, since the lexicon mixes in conjugated verbs,
  feminine forms, names and loanwords that no automatic rule separates well.
- Blocklists: LDNOOBW (en, pt) and fserb/pt-br listas/negativas, plus the
  reviewed exclusions below. NLTK's stopword lists drop function words.

Every word is stored in its real spelling; tiles use plain A-Z (see words.plain).
"""

import io
import re
import sys
import unicodedata
import urllib.request
import zipfile
from pathlib import Path

from wordfreq import zipf_frequency

ROOT = Path(__file__).parent.parent
CACHE = Path(__file__).parent / ".words-cache"
OUT = ROOT / "slid" / "words.py"
LENGTHS = (3, 4, 5, 6)
# English lists take the most frequent words per length, after exclusions. 3-letter words
# are scarcer, so they take everything above a frequency floor instead.
EN_PER_LENGTH = 600
EN_MIN_ZIPF = 3.3

URLS = {
    "12dicts.zip": "https://downloads.sourceforge.net/wordlist/12dicts-6.0.2.zip",
    "stopwords.zip": "https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/corpora/stopwords.zip",
    "bad-en": "https://raw.githubusercontent.com/LDNOOBW/List-of-Dirty-Naughty-Obscene-and-Otherwise-Bad-Words/master/en",
    "bad-pt": "https://raw.githubusercontent.com/LDNOOBW/List-of-Dirty-Naughty-Obscene-and-Otherwise-Bad-Words/master/pt",
    "pt-negativas": "https://raw.githubusercontent.com/fserb/pt-br/master/listas/negativas",
}

# Reviewed by hand from the frequency-ranked candidates: function words, interjections,
# abbreviations, names, slang, and words too sensitive or unpleasant for a daily puzzle.
EN_EXCLUDE = set("""
per via hey wow huh ugh bye yum aha woo boo gee coo yes may max bob sub sec rep con lib med
ref amp dis sic meg gal pee bra gay god wee bum fro bop

also must else upon thus onto till amid none john yeah okay damn hell mike dude crap piss
nope gosh blah whoa oops heck info mini prof stat prep temp sync dope coke babe dumb lame
gang jerk gore stud papa mama dame amen ping nick ford wont auto

would could might shall whose since among along hence gonna wanna gotta china trump smith
peter frank chuck homer mason welsh drake bible idiot loser naked sperm urine lynch slave
abuse screw nasty mommy daddy kitty freak legit inter hello corps midst

within either rather unless except beyond cannot anyway anyone nobody toward versus albeit
beside behalf namely awhile stupid racist racism killer murder virgin breast heroin bloody
filthy insane creepy warren walker victor cancer victim terror hatred ethnic savage potter
""".split())

# Kept by hand, in their real spelling: common base forms only (singular, masculine where an
# adjective has both, infinitives), no names, loanwords, adverbs or connectives.
PT_KEEP = {
    3: """
    dia bem ter ano ver vez bom rio boa dar lei fim uso sul rua mil mãe pai mês mal mão cor mar
    via sol paz dez voz som dor céu rei ato dom gol bar vir tom chá fio lua sal pão ama aço par
    gás mau cão lar mel rir voo tia ovo tio ida cem avó eco ave ira asa boi ego aro foz ler
    réu uva pia aba baú ala elo clã véu cru cal zoo giz noz vil oca ema nau oco ímã rum ipê ode
    pio duo bis
    """,
    4: """
    vida casa novo meio caso nome amor jogo três tipo país lado área água hora maio base rede
    foto data usar modo cara fato ação vale arte loja obra pena alto povo real tema nota fala
    medo vivo pele fase vila peso mesa moda café guia belo peça azul zona aula seis copa luta
    rosa boca alma fogo cama mapa tela sete leve cabo erro meia sede capa bola taxa dado dica
    liga lima ilha frio ruim doce vaga bebê juiz cena face grau oito voto olho solo chão útil
    amar foco mato moto flor menu luxo bolo caro lixo item irmã alvo zero cair cria piso dono
    ator fome papa nove neto saia topo roda sopa sono arma gato fone rico rumo teor papo meta
    cura agir seca gama raça anjo toca onda lago trem tiro seco lote neve fiel leão teto copo
    oral tese cola ramo gelo dose taça dedo duro moça sofá arco raio fita eixo dano lava suco
    caça selo fila anel fixo ódio vara pano coco raiz rota alho doze jato soja polo colo soma
    lobo dual euro mala inox raro trio saga crer fuga caos sapo voar feio fofo vela reta lata
    bota mito bico fino faca muro hino pneu cana unir juro tubo vaso maçã roxo galo poço unha
    pico leal giro onze dois reta
    """,
    5: """
    fazer tempo mundo forma parte feira coisa livro hotel final conta saber grupo lugar homem
    gente poder dizer geral noite filme preço local ficar valor curso corpo ponto falar março
    filho julho volta terra texto campo claro vídeo ajuda série carro tarde total lista venda
    certo nível busca gosto papel norte fácil linha frete amigo força idade causa livre fonte
    criar festa morte marca favor plano apoio manhã época santo forte longo cinco legal sexta
    autor porta lindo caixa único civil praia prova banco passo clube banda ordem prazo baixo
    fundo comum viver levar menor fórum jovem visão preto risco verde média ideia atual ouvir
    razão opção olhar médio setor tomar costa jogar mudar obter jeito leite terça ideal massa
    custo pagar sonho tirar filha rádio ótimo faixa verão crise casal velho mente globo abrir
    igual chave capaz troca breve corte sorte renda motor saída crime andar banho cargo roupa
    carta turma bolsa sinal disco teste canal reino irmão pedir carne termo chuva álbum folha
    rosto parar líder praça perda mídia aluno exame beijo vento etapa pegar chefe monte cheio
    resto queda carga vinho torno envio extra lazer museu clima achar dupla ferro rural placa
    ciclo senha oeste posto preso letra calor frase salão moral ponta humor metal botão canto
    toque dieta órgão curto culpa palco padre penal ética rocha ponte grave tocar solar couro
    ritmo seção aviso atriz cópia áudio creme bloco forno regra lança samba pasta vinte pobre
    sabor gerar peito rapaz fluxo cento beira avião ficha poeta fator anexo prato ligar pista
    anual arroz limpo justo bater braço lidar honra leste tênis conto nação norma bomba vírus
    molho lutar greve atuar calma poema fruto lucro fraco lavar noiva porte beber sítio golpe
    ativo calça móvel pleno barco tinta dever pesca vigor fugir sócio subir noção duplo magia
    vazio multa cinza milho louco virar turno banca senso torre metro amplo morar nobre votar
    coroa firme temer falha parto ganho drama arena limão herói raiva bolso casar juízo morro
    lição bispo colar elite trama tampa metrô pizza citar cobre ácido pauta missa lance navio
    fibra trigo nariz blusa cobra russo falso febre óbvio nuvem grego perna bicho roubo fruta
    lápis valer chato negar optar piada verbo forró notar batom chapa adeus grade mexer lenda
    apelo choro vapor curva pátio berço gripe piano gesto dólar grito ícone corda vital primo
    rever cupom ombro circo coral malha lento verso idoso fogão frota mania freio turnê trono
    êxito dente duque bacia golfe medir baile mover bando aéreo bônus tecla lente árabe dobro
    cesta porco pausa pacto vício grato fusão ruído fumar exato cruel altar grana terço abril
    junho cerca suave lesão digno suíte morte
    """,
    6: """
    grande cidade estado semana pessoa partir centro número mulher artigo acordo música região
    escola espaço senhor página frente início acesso imagem deixar quarto ensino igreja agosto
    equipe gestão quatro evento passar estudo versão chegar viagem código cabeça ajudar branco
    entrar estilo futuro título manter guerra seguir compra quinta mostra pensar voltar bairro
    sábado quarta função jornal enviar câmara defesa beleza efeito visita medida portal pedido
    cabelo cinema física tentar origem humano cartão ganhar rápido século sentir médico perder
    altura normal desejo classe contar dúvida perfil baixar parque evitar sangue motivo manual
    tornar buscar máximo espera padrão seguro quadro menina vender mínimo teatro abraço prazer
    diário marido guarda missão figura antigo pronto oferta ônibus aberto comida fiscal fechar
    resumo querer sessão amanhã enorme direto imóvel tabela teoria mestre regime prêmio visual
    metade quente janela parede animal começo jantar trazer global método década alugar esposa
    menino ataque índice triste grosso membro prisão paixão errado almoço açúcar acabar debate
    dormir leitor oração tratar tecido físico agenda agente poesia camisa chance chamar âmbito
    limite tópico pacote tarefa barato correr gostar garota câmera postar canção servir editar
    básico cuidar novela alerta pastor vencer prédio escala pecado ouvido árvore trocar viajar
    mental coelho colher curtir brilho famoso senado tomada cheiro núcleo rotina sombra treino
    rainha mandar elenco exibir cadeia sofrer causar planta cantor perigo lógica garoto queijo
    trilha clicar piloto rodada lançar álcool doutor reação milhão formar trecho montar escuro
    módulo minuto tensão parada emoção violão cavalo urbano eficaz cantar chorar ensaio editor
    boleto bacana ameaça marcar idioma limpar adulto coleta templo bebida filtro trinta colega
    atleta vestir margem mensal camada matriz cortar ficção frango apoiar panela provar testar
    azeite eterno aldeia juntar sonhar gastar doente adoção perdão choque atraso comitê nascer
    aposta relato avanço imenso marcha julgar pedaço mérito reunir ajuste doação atento pesado
    câmbio hábito gravar remoto formal cebola xícara válido outono acervo mágico marrom ilegal
    empate adesão buraco tomate gestor charme batata ofício namoro dançar inveja olhada oceano
    pintar variar sapato tapete queixa banana amante feijão barata ilusão atrair adotar quinto
    músico cartaz lógico varejo exigir quinze esfera boneca crença sentar ênfase surgir dragão
    virada gaúcho espada cobrar alarme romano queima tanque brinde caneta sorrir adorar toalha
    abrigo engano bronze descer enredo copiar escova leilão ocupar xadrez placar louvor pânico
    compor atacar salada pensão roubar recado antena típico apagar propor fresco livrar faltar
    futsal pressa tarifa cobrir operar balcão vacina pátria fumaça porção esgoto desvio célula
    mortal crochê postal morada encher tronco escuta jogada aliado oposto manejo troféu ritual
    balada doença língua dívida galera demora mágica chapéu fraude
    """,
}


def fetch(name: str) -> Path:
    path = CACHE / name
    if not path.exists():
        CACHE.mkdir(exist_ok=True)
        print(f"downloading {name}", file=sys.stderr)
        with urllib.request.urlopen(URLS[name], timeout=120) as resp:
            path.write_bytes(resp.read())
    return path


def zipped(archive: str, member: str, encoding: str) -> list[str]:
    with zipfile.ZipFile(fetch(archive)) as z:
        return io.TextIOWrapper(z.open(member), encoding=encoding).read().splitlines()


def plain(word: str) -> str:
    return unicodedata.normalize("NFKD", word).encode("ascii", "ignore").decode().upper()


def english() -> dict[int, list[str]]:
    heads = {line.strip() for line in zipped("12dicts.zip", "Lemmatized/2+2+3lem.txt", "latin-1") if not line.startswith(" ")}
    esl = {line.strip() for line in zipped("12dicts.zip", "American/3esl.txt", "latin-1")}
    stop = set(zipped("stopwords.zip", "stopwords/english", "utf-8"))
    bad = {w.strip().lower() for w in fetch("bad-en").read_text(encoding="utf-8").splitlines()}
    pool = [
        w for w in esl
        if re.fullmatch(r"[a-z]{3,6}", w) and w in heads and w not in stop | bad | EN_EXCLUDE
    ]
    scored = {w: zipf_frequency(w, "en") for w in pool}
    out = {}
    for n in LENGTHS:
        ranked = sorted((w for w in pool if len(w) == n and scored[w] >= EN_MIN_ZIPF), key=lambda w: (-scored[w], w))
        out[n] = ranked if n == 3 else ranked[:EN_PER_LENGTH]
    return out


def portuguese() -> dict[int, list[str]]:
    bad = {w.strip().lower() for w in fetch("bad-pt").read_text(encoding="utf-8").splitlines()}
    bad |= {w.strip().lower() for w in fetch("pt-negativas").read_text(encoding="utf-8").splitlines()}
    out = {}
    for n, words in PT_KEEP.items():
        kept, seen = [], set()
        for w in words.split():
            assert len(plain(w)) == n and plain(w).isalpha(), f"{w!r} doesn't fit {n} letters"
            assert w not in bad, f"{w!r} is on a blocklist"
            # Two spellings can share tiles (avó, avô): the first listed wins.
            if plain(w) not in seen:
                seen.add(plain(w))
                kept.append(w)
        out[n] = kept
    return out


def render(lists: dict[str, dict[int, list[str]]]) -> str:
    lines = [
        '"""Daily word pools, by language and word length. Generated by scripts/build_words.py; edit that, not this.',
        "",
        "Words keep their real spelling (PÃO); tiles use plain() of it (PAO). A word's length is its",
        'tile count. See scripts/build_words.py for sources and licenses."""',
        "",
        "import unicodedata",
        "",
        "",
        "def plain(word: str) -> str:",
        '    """The tile spelling of a word: uppercase A-Z, accents and cedillas dropped."""',
        '    return unicodedata.normalize("NFKD", word).encode("ascii", "ignore").decode().upper()',
        "",
        "",
        "WORDS: dict[str, dict[int, tuple[str, ...]]] = {",
    ]
    for lang, by_len in lists.items():
        lines.append(f"    {lang!r}: {{")
        for n, words in by_len.items():
            upper = sorted(w.upper() for w in words)
            lines.append(f"        {n}: (")
            row = "           "
            for w in upper:
                piece = f' "{w}",'
                if len(row) + len(piece) > 100:
                    lines.append(row)
                    row = "           "
                row += piece
            lines.append(row)
            lines.append("        ),")
        lines.append("    },")
    lines.append("}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    lists = {"en": english(), "pt-BR": portuguese()}
    OUT.write_text(render(lists), encoding="utf-8")
    for lang, by_len in lists.items():
        print(lang, {n: len(ws) for n, ws in by_len.items()})
