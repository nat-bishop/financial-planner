<script setup lang="ts">
import AppNav from './components/AppNav.vue'
import TwoFAModal from './components/TwoFAModal.vue'
</script>

<template>
  <div class="min-h-screen flex bg-surface-950">
    <AppNav />
    <main class="flex-1 ml-64 min-h-screen">
      <router-view />
    </main>
  </div>
  <TwoFAModal />
</template>
