import home from '../assets/art/home.png'
import scene from '../assets/art/scene.png'
import moon from '../assets/art/moon.png'
import cup from '../assets/art/cup.png'
import shadow from '../assets/art/shadow.png'
import mist from '../assets/art/mist.png'
import weicheng from '../assets/art/weicheng.png'
import jingting from '../assets/art/jingting.png'
import denggao from '../assets/art/denggao.png'
import fengqiao from '../assets/art/fengqiao.png'
import momei from '../assets/art/momei.png'
import cunju from '../assets/art/cunju.png'
import tianjingsha from '../assets/art/tianjingsha.png'
import linjiangxian from '../assets/art/linjiangxian.png'
import jihaizashi from '../assets/art/jihaizashi.png'
import rumengling from '../assets/art/rumengling.png'
import liangzhou from '../assets/art/liangzhou.png'

/**
 * 诗库。
 *
 * 约定：正文、释义、来源若为自拟，需用户审校史实（见 DEVLOG「未验证 / 风险」）。
 * 仅《水调歌头》自带 `acts` 与 `imagery`；其余篇目缺省时页面优雅降级。
 */

export type Dynasty = '唐' | '宋' | '元' | '明' | '清'

export type Genre =
  | '送别' | '边塞' | '思乡' | '山水' | '田园'
  | '咏月' | '怀古' | '羁旅' | '咏物' | '感怀'

export type ArtKey =
  | 'home' | 'scene' | 'moon' | 'cup' | 'shadow' | 'mist'
  | 'weicheng' | 'jingting' | 'denggao' | 'fengqiao' | 'momei' | 'cunju'
  | 'tianjingsha' | 'linjiangxian' | 'jihaizashi' | 'rumengling' | 'liangzhou'

export const ART: Record<ArtKey, string> = {
  home, scene, moon, cup, shadow, mist,
  weicheng, jingting, denggao, fengqiao, momei, cunju,
  tianjingsha, linjiangxian, jihaizashi, rumengling, liangzhou,
}

export interface Act { n: string; t: string }

export interface Imagery {
  name: string
  line: string
  clip: string
  note: string
  src: string
  art: ArtKey
}

export interface Poem {
  id: string
  title: string
  /** 词 → 上阕/下阕；曲 → 前段/后段；诗 → 前半/后半 */
  form: 'ci' | 'qu' | 'shi'
  author: string
  dynasty: Dynasty
  genre: Genre
  /** 首句，作副标题 */
  first: string
  preface?: string
  stanzas: [string[], string[]]
  /** 缺省 → 通用的「起 / 承 / 转」 */
  acts?: Act[]
  /** 缺省 → 意象段落整块不渲染 */
  imagery?: Imagery[]
  note?: string
  art: ArtKey
}

/** 三幕缺省值：无 `acts` 的篇目回退到通用结构 */
export const DEFAULT_ACTS: Act[] = [
  { n: '一', t: '起' },
  { n: '二', t: '承' },
  { n: '三', t: '转' },
]

export const actsOf = (p: Poem): Act[] => p.acts ?? DEFAULT_ACTS

export const POEMS: Poem[] = [
  {
    id: 'shuidiaogetou',
    title: '水调歌头',
    form: 'ci',
    author: '苏轼',
    dynasty: '宋',
    genre: '咏月',
    first: '明月几时有',
    preface: '丙辰中秋，欢饮达旦，大醉，作此篇，兼怀子由。',
    stanzas: [
      [
        '明月几时有？把酒问青天。',
        '不知天上宫阙，今夕是何年。',
        '我欲乘风归去，又恐琼楼玉宇，高处不胜寒。',
        '起舞弄清影，何似在人间。',
      ],
      [
        '转朱阁，低绮户，照无眠。',
        '不应有恨，何事长向别时圆？',
        '人有悲欢离合，月有阴晴圆缺，此事古难全。',
        '但愿人长久，千里共婵娟。',
      ],
    ],
    acts: [
      { n: '一', t: '把酒问月' },
      { n: '二', t: '欲往琼楼' },
      { n: '三', t: '清影与共月' },
    ],
    imagery: [
      {
        name: '明月', art: 'moon', line: '明月几时有？把酒问青天。',
        clip: '你在庭院抬头，月光落在杯沿，像一句尚未说完的问话。',
        note: '中秋之月象征团圆。苏轼作此词时，与弟弟苏辙已多年未见，月成为跨越距离的共同见证。',
        src: '《东坡乐府》；丙辰中秋词序',
      },
      {
        name: '酒杯', art: 'cup', line: '把酒问青天。',
        clip: '石桌上只一只青瓷杯，静待你举起。',
        note: '“把酒”即持酒杯。宋人常以酒入诗，借醉意抒写难以直言的情思。',
        src: '《苏轼词编年校注》',
      },
      {
        name: '清影', art: 'shadow', line: '起舞弄清影，何似在人间。',
        clip: '石径上的影子随你起落，仿佛另一个同行者。',
        note: '“清影”是月下独舞时的影子，诗人由此体会到人间的真实与可亲。',
        src: '《宋词三百首笺注》',
      },
    ],
    art: 'moon',
  },
  {
    id: 'songyuaner',
    title: '送元二使安西',
    form: 'shi',
    author: '王维',
    dynasty: '唐',
    genre: '送别',
    first: '渭城朝雨浥轻尘',
    stanzas: [
      ['渭城朝雨浥轻尘，', '客舍青青柳色新。'],
      ['劝君更尽一杯酒，', '西出阳关无故人。'],
    ],
    art: 'weicheng',
  },
  {
    id: 'liangzhouci',
    title: '凉州词',
    form: 'shi',
    author: '王翰',
    dynasty: '唐',
    genre: '边塞',
    first: '葡萄美酒夜光杯',
    stanzas: [
      ['葡萄美酒夜光杯，', '欲饮琵琶马上催。'],
      ['醉卧沙场君莫笑，', '古来征战几人回？'],
    ],
    art: 'liangzhou',
  },
  {
    id: 'denggao',
    title: '登高',
    form: 'shi',
    author: '杜甫',
    dynasty: '唐',
    genre: '感怀',
    first: '风急天高猿啸哀',
    stanzas: [
      [
        '风急天高猿啸哀，',
        '渚清沙白鸟飞回。',
        '无边落木萧萧下，',
        '不尽长江滚滚来。',
      ],
      [
        '万里悲秋常作客，',
        '百年多病独登台。',
        '艰难苦恨繁霜鬓，',
        '潦倒新停浊酒杯。',
      ],
    ],
    art: 'denggao',
  },
  {
    id: 'fengqiaoyebo',
    title: '枫桥夜泊',
    form: 'shi',
    author: '张继',
    dynasty: '唐',
    genre: '羁旅',
    first: '月落乌啼霜满天',
    stanzas: [
      ['月落乌啼霜满天，', '江枫渔火对愁眠。'],
      ['姑苏城外寒山寺，', '夜半钟声到客船。'],
    ],
    art: 'fengqiao',
  },
  {
    id: 'jingtingshan',
    title: '独坐敬亭山',
    form: 'shi',
    author: '李白',
    dynasty: '唐',
    genre: '山水',
    first: '众鸟高飞尽',
    stanzas: [
      ['众鸟高飞尽，', '孤云独去闲。'],
      ['相看两不厌，', '只有敬亭山。'],
    ],
    art: 'jingting',
  },
  {
    id: 'rumengling',
    title: '如梦令',
    form: 'ci',
    author: '李清照',
    dynasty: '宋',
    genre: '田园',
    first: '常记溪亭日暮',
    stanzas: [
      ['常记溪亭日暮，', '沉醉不知归路。', '兴尽晚回舟，', '误入藕花深处。'],
      ['争渡，争渡，', '惊起一滩鸥鹭。'],
    ],
    art: 'rumengling',
  },
  {
    id: 'linjiangxian',
    title: '临江仙',
    form: 'ci',
    author: '杨慎',
    dynasty: '明',
    genre: '怀古',
    first: '滚滚长江东逝水',
    stanzas: [
      [
        '滚滚长江东逝水，浪花淘尽英雄。',
        '是非成败转头空。',
        '青山依旧在，几度夕阳红。',
      ],
      [
        '白发渔樵江渚上，惯看秋月春风。',
        '一壶浊酒喜相逢。',
        '古今多少事，都付笑谈中。',
      ],
    ],
    art: 'linjiangxian',
  },
  {
    id: 'tianjingsha',
    title: '天净沙·秋思',
    form: 'qu',
    author: '马致远',
    dynasty: '元',
    genre: '思乡',
    first: '枯藤老树昏鸦',
    stanzas: [
      ['枯藤老树昏鸦，', '小桥流水人家，', '古道西风瘦马。'],
      ['夕阳西下，', '断肠人在天涯。'],
    ],
    art: 'tianjingsha',
  },
  {
    id: 'momei',
    title: '墨梅',
    form: 'shi',
    author: '王冕',
    dynasty: '元',
    genre: '咏物',
    first: '我家洗砚池头树',
    stanzas: [
      ['我家洗砚池头树，', '朵朵花开淡墨痕。'],
      ['不要人夸好颜色，', '只留清气满乾坤。'],
    ],
    art: 'momei',
  },
  {
    id: 'jihaizashi',
    title: '己亥杂诗',
    form: 'shi',
    author: '龚自珍',
    dynasty: '清',
    genre: '感怀',
    first: '浩荡离愁白日斜',
    stanzas: [
      ['浩荡离愁白日斜，', '吟鞭东指即天涯。'],
      ['落红不是无情物，', '化作春泥更护花。'],
    ],
    art: 'jihaizashi',
  },
  {
    id: 'cunju',
    title: '村居',
    form: 'shi',
    author: '高鼎',
    dynasty: '清',
    genre: '田园',
    first: '草长莺飞二月天',
    stanzas: [
      ['草长莺飞二月天，', '拂堤杨柳醉春烟。'],
      ['儿童散学归来早，', '忙趁东风放纸鸢。'],
    ],
    art: 'cunju',
  },
]

export const poemById = (id: string | undefined): Poem | undefined =>
  id ? POEMS.find((p) => p.id === id) : undefined

/** 全部句子展平，供进度三态（已体验 / 当前 / 后续）使用 */
export const allLines = (p: Poem): string[] => [...p.stanzas[0], ...p.stanzas[1]]

export const totalLines = (p: Poem): number => p.stanzas[0].length + p.stanzas[1].length

/** 筛选维度取值（按诗库出现顺序去重） */
export const facets = {
  genre: [...new Set(POEMS.map((p) => p.genre))],
  author: [...new Set(POEMS.map((p) => p.author))],
  dynasty: [...new Set(POEMS.map((p) => p.dynasty))],
}
