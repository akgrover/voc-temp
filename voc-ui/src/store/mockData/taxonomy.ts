export type TaxonomyNode = {
  id: string
  label: string
  parentId: string | null
  unitCount: number
  trend: string
  status: 'active' | 'candidate'
  confidenceAvg?: number
}

export const MOCK_TAXONOMY: TaxonomyNode[] = [
  // --- Pillars (Level 0) ---
  { id: 'tax-performance', label: 'Performance', parentId: null, unitCount: 312, trend: '+18%', status: 'active', confidenceAvg: 0.91 },
  { id: 'tax-auth', label: 'Authentication', parentId: null, unitCount: 201, trend: '+12%', status: 'active', confidenceAvg: 0.89 },
  { id: 'tax-data', label: 'Data Management', parentId: null, unitCount: 178, trend: '-6%', status: 'active', confidenceAvg: 0.87 },
  { id: 'tax-cx', label: 'Customer Experience', parentId: null, unitCount: 256, trend: '+8%', status: 'active', confidenceAvg: 0.85 },

  // --- Categories under Performance ---
  { id: 'tax-report-export', label: 'Report Export', parentId: 'tax-performance', unitCount: 143, trend: '+34%', status: 'active', confidenceAvg: 0.93 },
  { id: 'tax-dashboard-load', label: 'Dashboard Loading', parentId: 'tax-performance', unitCount: 89, trend: '0%', status: 'active', confidenceAvg: 0.90 },
  { id: 'tax-search-speed', label: 'Search Speed', parentId: 'tax-performance', unitCount: 80, trend: '+4%', status: 'active', confidenceAvg: 0.88 },

  // --- Categories under Authentication ---
  { id: 'tax-login-fail', label: 'Login Failures', parentId: 'tax-auth', unitCount: 95, trend: '+12%', status: 'active', confidenceAvg: 0.92 },
  { id: 'tax-sso', label: 'SSO Integration', parentId: 'tax-auth', unitCount: 67, trend: '+18%', status: 'active', confidenceAvg: 0.88 },
  { id: 'tax-session', label: 'Session Timeouts', parentId: 'tax-auth', unitCount: 39, trend: '0%', status: 'active', confidenceAvg: 0.85 },

  // --- Categories under Data Management ---
  { id: 'tax-csv-import', label: 'CSV Import Errors', parentId: 'tax-data', unitCount: 98, trend: '-8%', status: 'active', confidenceAvg: 0.90 },
  { id: 'tax-bulk-edit', label: 'Bulk Edit', parentId: 'tax-data', unitCount: 80, trend: '-6%', status: 'active', confidenceAvg: 0.84 },

  // --- Categories under Customer Experience ---
  { id: 'tax-onboarding', label: 'Onboarding Flow', parentId: 'tax-cx', unitCount: 72, trend: '+9%', status: 'active', confidenceAvg: 0.86 },
  { id: 'tax-pricing', label: 'Pricing Concerns', parentId: 'tax-cx', unitCount: 28, trend: '+17%', status: 'active', confidenceAvg: 0.82 },
  { id: 'tax-support-resp', label: 'Support Response', parentId: 'tax-cx', unitCount: 64, trend: '+41%', status: 'active', confidenceAvg: 0.89 },
  { id: 'tax-api-docs', label: 'API Documentation', parentId: 'tax-cx', unitCount: 55, trend: '0%', status: 'active', confidenceAvg: 0.87 },
  { id: 'tax-mobile-offline', label: 'Mobile Offline', parentId: 'tax-cx', unitCount: 37, trend: '+21%', status: 'active', confidenceAvg: 0.80 },

  // --- Themes under Report Export (Level 2) ---
  { id: 'tax-export-timeout', label: 'Export Timeout', parentId: 'tax-report-export', unitCount: 68, trend: '+42%', status: 'active', confidenceAvg: 0.94 },
  { id: 'tax-export-format', label: 'Export Format Support', parentId: 'tax-report-export', unitCount: 45, trend: '+22%', status: 'active', confidenceAvg: 0.91 },
  { id: 'tax-export-size', label: 'Large File Handling', parentId: 'tax-report-export', unitCount: 30, trend: '+28%', status: 'active', confidenceAvg: 0.93 },

  // --- Themes under Login Failures (Level 2) ---
  { id: 'tax-login-sso-break', label: 'Post-Deploy SSO Failures', parentId: 'tax-login-fail', unitCount: 52, trend: '+65%', status: 'active', confidenceAvg: 0.95 },
  { id: 'tax-login-mfa', label: 'MFA Token Issues', parentId: 'tax-login-fail', unitCount: 43, trend: '-3%', status: 'active', confidenceAvg: 0.88 },

  // --- Unclassified ---
  { id: 'tax-unclassified', label: 'Unclassified', parentId: null, unitCount: 24, trend: '', status: 'candidate', confidenceAvg: 0.52 },
]
