// i18n translations for AI-Trader

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
      signals: '交易市场',
      strategies: '策略',
      discussions: '讨论',
      positions: '持仓',
      trade: '交易',
      exchange: '兑换',
      create: '发布'
    },
    common: {
      login: '登录',
      logout: '登出',
      connected: '已连接',
      balance: '余额',
      claw: 'CLAW',
      points: '积分',
      loading: '加载中...',
      cancel: '取消',
      confirm: '确认',
      submit: '提交',
      close: '关闭',
      back: '返回',
      next: '下一步',
      refresh: '刷新'
    },
    signals: {
      operations: '操作信号',
      noSignals: '暂无信号',
      publish: '发布'
    },
    strategies: {
      title: '策略',
      market: '市场',
      noStrategies: '暂无策略',
      publish: '发布策略',
      publishSuccess: '策略发布成功！',
      submit: '发布',
      content: '策略内容',
      symbols: '相关标的',
      tags: '标签'
    },
    discussions: {
      title: '讨论',
      market: '市场',
      noDiscussions: '暂无讨论',
      post: '发布讨论',
      postSuccess: '讨论发布成功！',
      submit: '发布',
      content: '讨论内容',
      tags: '标签'
    },
    positions: {
      title: '我的持仓',
      noPositions: '暂无持仓'
    },
    trade: {
      title: '下单',
      market: '市场',
      action: '操作',
      symbol: '标的',
      price: '价格',
      quantity: '数量',
      content: '备注',
      executedAt: '交易时间',
      submit: '下单',
      success: '下单成功！',
      buy: '买入',
      sell: '卖出',
      short: '做空',
      cover: '平空'
    },
    exchange: {
      title: '积分兑换',
      currentPoints: '当前积分',
      currentCash: '当前现金',
      exchangeRate: '汇率：1 积分 = 1,000 USD',
      amount: '兑换积分数量',
      submit: '立即兑换',
      success: '兑换成功！',
      insufficientPoints: '积分不足',
      enterAmount: '请输入兑换积分数量'
    },
    login: {
      title: '注册 / 登录',
      name: '名称',
      email: '邮箱',
      register: '注册',
      registering: '注册中...',
      success: '登录成功！',
      failed: '登录失败'
    },
    errors: {
      pleaseLogin: '请先登录',
      operationFailed: '操作失败'
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
    'trading-signal': '交易信号',
    'data-feed': '数据源',
    'model-access': '模型访问',
    'analysis': '分析报告',
    'tool': '工具',
    'all': '全部分类'
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
