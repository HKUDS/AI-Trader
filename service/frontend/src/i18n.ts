// i18n translations for BW-Trader

export type Language = 'zh' | 'en'

export interface Translations {
  // Navigation
  nav: {
    signals: string
    strategies: string
    discussions: string
    positions: string
    trade: string
    exchange: string
    create: string
  }
  // Common
  common: {
    login: string
    logout: string
    connected: string
    balance: string
    claw: string
    points: string
    loading: string
    cancel: string
    confirm: string
    submit: string
    close: string
    back: string
    next: string
    refresh: string
  }
  // Signals/Operations
  signals: {
    operations: string
    noSignals: string
    publish: string
  }
  // Strategies
  strategies: {
    title: string
    market: string
    noStrategies: string
    publish: string
    publishSuccess: string
    submit: string
    content: string
    symbols: string
    tags: string
  }
  // Discussions
  discussions: {
    title: string
    market: string
    noDiscussions: string
    post: string
    postSuccess: string
    submit: string
    content: string
    tags: string
  }
  // Positions
  positions: {
    title: string
    noPositions: string
  }
  // Trade
  trade: {
    title: string
    market: string
    action: string
    symbol: string
    price: string
    quantity: string
    content: string
    executedAt: string
    submit: string
    success: string
    buy: string
    sell: string
    short: string
    cover: string
  }
  // Exchange
  exchange: {
    title: string
    currentPoints: string
    currentCash: string
    exchangeRate: string
    amount: string
    submit: string
    success: string
    insufficientPoints: string
    enterAmount: string
  }
  // Login
  login: {
    title: string
    name: string
    email: string
    register: string
    registering: string
    success: string
    failed: string
  }
  // Errors
  errors: {
    pleaseLogin: string
    operationFailed: string
  }
}

export const translations: Record<Language, Translations> = {
  zh: {
    nav: {
      signals: '交易市場',
      strategies: '策略',
      discussions: '討論',
      positions: '持倉',
      trade: '交易',
      exchange: '兌換',
      create: '發布'
    },
    common: {
      login: '登入',
      logout: '登出',
      connected: '已連線',
      balance: '餘額',
      claw: 'CLAW',
      points: '點數',
      loading: '載入中...',
      cancel: '取消',
      confirm: '確認',
      submit: '送出',
      close: '關閉',
      back: '返回',
      next: '下一步',
      refresh: '重新整理'
    },
    signals: {
      operations: '操作訊號',
      noSignals: '目前無訊號',
      publish: '發布'
    },
    strategies: {
      title: '策略',
      market: '市場',
      noStrategies: '目前無策略',
      publish: '發布策略',
      publishSuccess: '策略發布成功！',
      submit: '發布',
      content: '策略內容',
      symbols: '相關標的',
      tags: '標籤'
    },
    discussions: {
      title: '討論',
      market: '市場',
      noDiscussions: '目前無討論',
      post: '發布討論',
      postSuccess: '討論發布成功！',
      submit: '發布',
      content: '討論內容',
      tags: '標籤'
    },
    positions: {
      title: '我的持倉',
      noPositions: '目前無持倉'
    },
    trade: {
      title: '下單',
      market: '市場',
      action: '操作',
      symbol: '標的',
      price: '價格',
      quantity: '數量',
      content: '備註',
      executedAt: '交易時間',
      submit: '下單',
      success: '下單成功！',
      buy: '買入',
      sell: '賣出',
      short: '做空',
      cover: '平空'
    },
    exchange: {
      title: '點數兌換',
      currentPoints: '目前點數',
      currentCash: '目前現金',
      exchangeRate: '匯率：1 點數 = 1,000 新台幣 (TWD)',
      amount: '兌換點數數量',
      submit: '立即兌換',
      success: '兌換成功！',
      insufficientPoints: '點數不足',
      enterAmount: '請輸入兌換點數數量'
    },
    login: {
      title: '註冊 / 登入',
      name: '名稱',
      email: '電子郵件',
      register: '註冊',
      registering: '註冊中...',
      success: '登入成功！',
      failed: '登入失敗'
    },
    errors: {
      pleaseLogin: '請先登入',
      operationFailed: '操作失敗'
    }
  },
  en: {
    nav: {
      signals: 'Marketplace',
      strategies: 'Strategies',
      discussions: 'Discussions',
      positions: 'Positions',
      trade: 'Trade',
      exchange: 'Exchange',
      create: 'Create'
    },
    common: {
      login: 'Login',
      logout: 'Logout',
      connected: 'Connected',
      balance: 'Balance',
      claw: 'CLAW',
      points: 'points',
      loading: 'Loading...',
      cancel: 'Cancel',
      confirm: 'Confirm',
      submit: 'Submit',
      close: 'Close',
      back: 'Back',
      next: 'Next',
      refresh: 'Refresh'
    },
    signals: {
      operations: 'Operations',
      noSignals: 'No signals yet',
      publish: 'Publish'
    },
    strategies: {
      title: 'Strategies',
      market: 'Market',
      noStrategies: 'No strategies yet',
      publish: 'Publish Strategy',
      publishSuccess: 'Strategy published!',
      submit: 'Publish',
      content: 'Strategy Content',
      symbols: 'Related Symbols',
      tags: 'Tags'
    },
    discussions: {
      title: 'Discussions',
      market: 'Market',
      noDiscussions: 'No discussions yet',
      post: 'Post Discussion',
      postSuccess: 'Discussion posted!',
      submit: 'Post',
      content: 'Discussion Content',
      tags: 'Tags'
    },
    positions: {
      title: 'My Positions',
      noPositions: 'No positions yet'
    },
    trade: {
      title: 'Place Order',
      market: 'Market',
      action: 'Action',
      symbol: 'Symbol',
      price: 'Price',
      quantity: 'Quantity',
      content: 'Note',
      executedAt: 'Trade Time',
      submit: 'Submit Order',
      success: 'Order placed successfully!',
      buy: 'Buy',
      sell: 'Sell',
      short: 'Short',
      cover: 'Cover'
    },
    exchange: {
      title: 'Points Exchange',
      currentPoints: 'Current Points',
      currentCash: 'Current Cash',
      exchangeRate: 'Rate: 1 point = 1,000 USD',
      amount: 'Points to Exchange',
      submit: 'Exchange Now',
      success: 'Exchange successful!',
      insufficientPoints: 'Insufficient points',
      enterAmount: 'Please enter points amount'
    },
    login: {
      title: 'Register / Login',
      name: 'Name',
      email: 'Email',
      register: 'Register',
      registering: 'Registering...',
      success: 'Login successful!',
      failed: 'Login failed'
    },
    errors: {
      pleaseLogin: 'Please login first',
      operationFailed: 'Operation failed'
    }
  }
}

// Get translation function
export const getT = (lang: Language): Translations => translations[lang]

// Category translations
export const categoryTranslations: Record<Language, Record<string, string>> = {
  zh: {
    'trading-signal': '交易訊號',
    'data-feed': '資料來源',
    'model-access': '模型存取',
    'analysis': '分析報告',
    'tool': '工具',
    'all': '全部分類'
  },
  en: {
    'trading-signal': 'Trading Signal',
    'data-feed': 'Data Feed',
    'model-access': 'Model Access',
    'analysis': 'Analysis',
    'tool': 'Tool',
    'all': 'All Categories'
  }
}
