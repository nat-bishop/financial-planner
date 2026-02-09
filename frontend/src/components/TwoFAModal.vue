<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import { useSyncStore } from '../stores/sync'

const syncStore = useSyncStore()
const code = ref('')
const inputRef = ref<HTMLInputElement | null>(null)

// Auto-focus input when modal appears
watch(() => syncStore.twoFaPending, async (pending) => {
  if (pending) {
    code.value = ''
    await nextTick()
    inputRef.value?.focus()
  }
})

async function submit() {
  if (!code.value.trim()) return
  await syncStore.submit2FACode(code.value.trim())
  code.value = ''
}

function cancel() {
  syncStore.dismiss2FA()
}

function methodLabel(method: string | null): string {
  switch (method) {
    case 'sms': return 'SMS'
    case 'email': return 'Email'
    case 'authenticator': return 'Authenticator'
    default: return 'Verification'
  }
}
</script>

<template>
  <Teleport to="body">
    <Transition name="modal">
      <div
        v-if="syncStore.twoFaPending"
        class="fixed inset-0 z-50 flex items-center justify-center"
      >
        <!-- Backdrop -->
        <div class="absolute inset-0 bg-surface-0/80 backdrop-blur-sm" @click="cancel" />

        <!-- Modal card -->
        <div class="relative w-full max-w-sm mx-4 bg-surface-50 border border-surface-200/50 rounded-2xl p-6 shadow-2xl">
          <!-- Icon + header -->
          <div class="flex flex-col items-center text-center mb-6">
            <div class="w-12 h-12 bg-info/10 rounded-xl flex items-center justify-center mb-3">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" class="text-info">
                <path d="M12 2L4 7v5c0 5.55 3.42 10.74 8 12 4.58-1.26 8-6.45 8-12V7l-8-5z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
                <path d="M9 12l2 2 4-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
            </div>
            <h2 class="text-base font-medium text-surface-900">Verification Required</h2>
            <div class="mt-1 inline-flex items-center gap-1.5 px-2.5 py-0.5 bg-info/10 rounded-full">
              <div class="w-1.5 h-1.5 rounded-full bg-info animate-pulse"></div>
              <span class="text-xs font-medium text-info">{{ methodLabel(syncStore.twoFaMethod) }}</span>
            </div>
          </div>

          <!-- Prompt text -->
          <p class="text-sm text-surface-500 text-center mb-5 leading-relaxed">
            {{ syncStore.twoFaPrompt || 'Enter the verification code to continue syncing.' }}
          </p>

          <!-- Code input -->
          <div class="mb-4">
            <input
              ref="inputRef"
              v-model="code"
              type="text"
              inputmode="numeric"
              autocomplete="one-time-code"
              placeholder="000000"
              maxlength="10"
              class="w-full px-4 py-3 bg-surface-100 border border-surface-200 rounded-xl text-center text-lg font-mono tracking-[0.3em] text-surface-900 placeholder:text-surface-400 focus:outline-none focus:ring-2 focus:ring-info/50 focus:border-info transition-colors"
              :class="{ 'border-expense focus:ring-expense/50 focus:border-expense': syncStore.twoFaError }"
              :disabled="syncStore.twoFaSubmitting"
              @keyup.enter="submit"
            />
          </div>

          <!-- Error message -->
          <p v-if="syncStore.twoFaError" class="text-xs text-expense font-mono text-center mb-4">
            {{ syncStore.twoFaError }}
          </p>

          <!-- Actions -->
          <div class="flex gap-3">
            <button
              @click="cancel"
              class="flex-1 px-4 py-2.5 text-sm font-medium text-surface-500 bg-surface-100 rounded-xl transition-all duration-200 hover:bg-surface-200 active:scale-[0.98]"
            >
              Cancel
            </button>
            <button
              @click="submit"
              :disabled="!code.trim() || syncStore.twoFaSubmitting"
              class="flex-1 px-4 py-2.5 text-sm font-medium bg-info text-surface-0 rounded-xl transition-all duration-200 hover:brightness-110 active:scale-[0.98]"
              :class="{ 'opacity-60 cursor-wait': syncStore.twoFaSubmitting, 'opacity-40 cursor-not-allowed': !code.trim() }"
            >
              {{ syncStore.twoFaSubmitting ? 'Verifying...' : 'Verify' }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.2s ease;
}
.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}
</style>
