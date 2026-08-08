export interface AdminCredentials {
  email: string
  password: string
}

export const emptyAdminCredentials: AdminCredentials = {
  email: '',
  password: '',
}
