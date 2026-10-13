import { createRouter, createWebHistory } from 'vue-router'
import Home from '../views/Home.vue'
import Setup from '../views/Setup.vue'
import Interview from '../views/Interview.vue'
import Report from '../views/Report.vue'
import History from '../views/History.vue'

const routes = [
  { path: '/', component: Home },
  { path: '/setup', component: Setup },
  { path: '/interview/:id', component: Interview },
  { path: '/report/:id', component: Report },
  { path: '/history', component: History },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
