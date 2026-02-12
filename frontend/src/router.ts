import { createRouter, createWebHistory } from 'vue-router'
import DashboardView from './views/DashboardView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'dashboard',
      component: DashboardView,
    },
    {
      path: '/transactions',
      name: 'transactions',
      component: () => import('./views/TransactionsView.vue'),
    },
    {
      path: '/accounts',
      name: 'accounts',
      component: () => import('./views/AccountsView.vue'),
    },
    {
      path: '/projection',
      name: 'projection',
      component: () => import('./views/ProjectionView.vue'),
    },
    {
      path: '/settings',
      name: 'settings',
      component: () => import('./views/SettingsView.vue'),
    },
  ],
})
