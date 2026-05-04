<template>
  <div class="interaction-page">
    <div class="page-shell">
      <section class="lane lane-left">
        <header class="lane-head">
          <div class="lane-heading">
            <div class="lane-kicker">Flow</div>
            <h2 class="lane-title">节点</h2>
          </div>
          <div style="display: flex; gap: 8px; align-items: center;">
            <button
              v-if="nodeMessages.length > 0"
              type="button"
              class="reset-btn"
              @click="handleReset"
              title="重置会话"
            >
              🔄
            </button>
            <span class="status-pill" :class="{ online: isConnected }">
              {{ isConnected ? "WS 已连接" : "WS 未连接" }}
            </span>
          </div>
        </header>

        <div class="lane-body node-list">
          <div
            ref="nodeScrollEl"
            class="node-scroll"
            @scroll="handleNodeScroll"
          >
            <div v-if="!nodeMessages.length" class="empty-state">
              等待节点开始流转
            </div>

            <div
              v-for="(msg, index) in nodeMessages"
              :key="`${msg}-${index}`"
              class="node-row"
              :class="{
                clickable: isHasMsg(msg),
                active: dialogVisible && selectedMsg === msg,
              }"
              @click="handleNodeClick(msg)"
            >
              <NodeComponent
                :isLoading="index == nodeMessages.length - 1"
                :isMsg="isHasMsg(msg)"
                :meta="msg"
                :text="nodeNameToReadable(msg)"
                description="正在处理中..."
              />
            </div>
          </div>
        </div>
      </section>

      <section class="lane lane-center">
        <div class="lane-body stream-stack">
          <div class="stream-switch" role="tablist" aria-label="流式输出切换">
            <button
              type="button"
              class="stream-tab"
              :class="{
                active: selectedStreamKey === 'background',
                populated: !!backgroundText,
              }"
              @click="selectStream('background')"
            >
              <span class="stream-tab-kicker">Background</span>
              <span class="stream-tab-title">{{ nodeNameToReadable("background_node") }}</span>
            </button>
            <button
              type="button"
              class="stream-tab"
              :class="{
                active: selectedStreamKey === 'continue',
                populated: !!continueText,
              }"
              @click="selectStream('continue')"
            >
              <span class="stream-tab-kicker">Continue</span>
              <span class="stream-tab-title">{{ nodeNameToReadable("continue_next_node") }}</span>
            </button>
          </div>

          <div class="stream-stage">
            <Transition name="card-slide" mode="out-in">
              <section :key="selectedStreamKey" class="stream-section stream-section-single">
                <LetterComponent
                  v-if="selectedStreamMeta.content"
                  :meta="selectedStreamMeta.meta"
                  :text="selectedStreamMeta.title"
                  :content="selectedStreamMeta.content"
                />
                <div v-else class="empty-state empty-state-large">
                  {{ selectedStreamMeta.emptyText }}
                </div>
              </section>
            </Transition>
          </div>
        </div>
      </section>

      <section class="lane lane-right">
        <header class="lane-head">
          <div class="lane-heading">
            <div class="lane-kicker">Roles</div>
            <h2 class="lane-title">角色发言</h2>
          </div>
          <span class="status-pill subtle">{{ roleMessages.length }} 条</span>
        </header>

        <div class="lane-body speech-list">
          <div v-if="!roleMessages.length" class="empty-state">
            暂无角色发言
          </div>

          <div v-for="(item, index) in roleMessages" :key="index" class="speech-row">
            <RoleSpeechComponent :roleName="item.roleName" :speech="item.text" />
          </div>
        </div>
      </section>
    </div>

    <div v-if="dialogVisible" class="dialog-mask" @click.self="closeDialog">
      <div class="dialog-container dialog-single">
        <LetterComponent
          v-if="selectedMsg === 'background_node'"
          :meta="selectedMsg"
          :text="nodeNameToReadable(selectedMsg)"
          :content="backgroundText"
        />
        <LetterComponent
          v-else-if="selectedMsg === 'continue_next_node'"
          :meta="selectedMsg"
          :text="nodeNameToReadable(selectedMsg)"
          :content="continueText"
        />
        <SearchContentComponent
          v-else-if="selectedMsg === 'search_node'"
          :content="searchContent || '暂无搜索结果。'"
        />
        <div v-else class="dialog-fallback">暂无可展示的消息：{{ selectedMsg }}</div>
        <button type="button" class="close-btn" @click="closeDialog">关闭</button>
      </div>
    </div>

    <div v-if="pendingQuestion" class="dialog-mask">
      <div class="dialog-container dialog-center">
        <QaNoteComponent
          v-if="pendingQuestion"
          :meta="pendingQuestion.meta"
          :role="pendingQuestion.role"
          :question="pendingQuestion.question"
          :disabled="!isConnected"
          @submit="handleUserAnswer"
        />
      </div>
    </div>

    <div
      v-if="choiceDialogVisible && choiceItems.length"
      class="dialog-mask"
      @click.self="closeDialog"
    >
      <div class="dialog-container dialog-stack">
        <CriticalMomentComponent
          v-for="(item, index) in choiceItems"
          :key="index"
          :title="item.key_moment"
          :leftChoice="item.original_action"
          :rightChoices="[item.alternative_action]"
          @submit="handleChoiceSubmit"
        />
      </div>
    </div>

    <div v-if="pendingRole" class="dialog-mask">
      <div class="dialog-container dialog-center">
        <QaNoteComponent
          v-if="pendingRole"
          :meta="pendingRole.field"
          :role="pendingRole.role_name"
          :question="pendingRole.question"
          :disabled="!isConnected"
          @submit="handleRoleReply"
        />
      </div>
    </div>

    <div v-if="experienceDialogVisible" class="dialog-mask">
      <div class="dialog-container dialog-center">
        <ExperienceComponent :disabled="!isConnected" @submit="handleExperienceSubmit" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch, onMounted } from "vue";
import { useDooverWs } from "../composables/useDooverWs";
import NodeComponent from "../components/NodeComponent.vue";
import LetterComponent from "../components/LetterComponent.vue";
import QaNoteComponent from "../components/QaNoteComponent.vue";
import RoleSpeechComponent from "../components/RoleSpeechComponent.vue";
import CriticalMomentComponent from "../components/CriticalMomentComponent.vue";
import SearchContentComponent from "../components/SearchContentComponent.vue";
import ExperienceComponent from "../components/ExperienceComponent.vue";

const dialogVisible = ref(false);
const selectedMsg = ref(null);
const nodeScrollEl = ref(null);
const shouldStickNodeScroll = ref(true);
let nodeScrollFrameId = null;
const experienceDialogVisible = ref(true);

const handleNodeClick = (msg) => {
  // 只允许点击 isMsg 为 true 的节点弹出
  if (!isHasMsg(msg)) return;
  selectedMsg.value = msg;
  dialogVisible.value = true;
};

const closeDialog = () => {
  dialogVisible.value = false;
  choiceDialogVisible.value = false;
  selectedMsg.value = null;
  pendingQuestion.value = null;
  pendingRole.value = null;
  pendingChoices.value = [];
};

const choiceDialogVisible = ref(false);
const handleChoiceSubmit = (choiceText, index) => {
  if (!isConnected.value) return;
  sendUserChoice(choiceText, index);
  choiceDialogVisible.value = false;
};

const handleUserAnswer = (answer) => {
  if (!isConnected.value) return;
  sendUserAnswer(answer);
};

const handleRoleReply = (answer) => {
  if (!isConnected.value) return;
  sendRoleReply(answer);
};

const handleExperienceSubmit = (text) => {
  if (!isConnected.value) return;
  sendUserInput(text);
  experienceDialogVisible.value = false;
};
const isHasMsg = (msg) => {
  if (
    msg === "background_node" ||
    msg === "continue_next_node" ||
    msg === "search_node"
  )
    return true;
  return false;
};

//节点名称转可读函数
const nodeNameToReadable = (msg) => {
  const nodeNameMap = {
    login_success_node: "登录成功节点",
    init_world_params: "世界参数初始化节点",
    intake_node: "输入接收节点",
    background_node: "背景信息节点",
    agent_node: "工具决策节点",
    tool_node: "工具执行节点",
    wait_user_node: "等待用户补充节点",
    turn_node: "转折事件生成节点",
    user_choice_node: "用户选择节点",
    create_role_node: "角色创建节点",
    role_node: "角色推演节点",
    analyze_interaction_node: "角色互动分析节点",
    tool_node2: "角色互动工具节点",
    wait_for_interaction_node: "等待角色互动节点",
    continue_next_node: "继续推理节点",
    tool_node3: "继续推理工具节点",
    wait_for_interaction_from_continue: "继续推理等待互动节点",
    should_continue: "继续判断节点",
    should_wait_for_user: "用户等待判断节点",
    should_wait_for_role_interaction: "角色互动等待判断节点",
    search_node: "搜索节点",
  };
  return nodeNameMap[msg] || msg;
};
const {
  isConnected,
  pendingQuestion,
  pendingRole,
  pendingChoices,
  nodeMessages,
  roleMessages,
  backgroundText,
  continueText,
  searchContent,
  sendUserInput,
  sendUserAnswer,
  sendUserChoice,
  sendRoleReply,
  resetSession,
  restoreState,
  hasSavedState,
} = useDooverWs();

const handleReset = () => {
  if (confirm("确定要重置会话吗？所有历史记录将被清空。")) {
    closeDialog();
    resetSession();
    experienceDialogVisible.value = true;
  }
};

// 组件挂载时恢复状态
onMounted(() => {
  restoreState();
});

// 监听恢复的 pendingQuestion 并显示对话框
watch(pendingQuestion, (val) => {
  if (val) {
    // pendingQuestion 已经包含数据，组件会自动显示对话框
  }
});

// 监听恢复的 pendingChoices 并显示对话框
watch(pendingChoices, (val) => {
  if (val && val.length > 0) {
    choiceDialogVisible.value = true;
  }
});

// 监听恢复的 pendingRole 并显示对话框
watch(pendingRole, (val) => {
  if (val) {
    // pendingRole 已经包含数据，组件会自动显示对话框
  }
});

// 只有在没有保存状态时才显示初始输入对话框
watch(hasSavedState, (val) => {
  if (val && nodeMessages.value.length > 0) {
    experienceDialogVisible.value = false;
  }
});

const choiceItems = computed(() => {
  if (Array.isArray(pendingChoices.value)) return pendingChoices.value;
  if (Array.isArray(pendingChoices.value?.items)) return pendingChoices.value.items;
  return [];
});

const selectedStreamKey = ref("background");

const selectStream = (key) => {
  selectedStreamKey.value = key;
};

const selectedStreamMeta = computed(() => {
  if (selectedStreamKey.value === "continue") {
    return {
      key: "continue",
      meta: "continue_next_node",
      kicker: "Continue",
      title: nodeNameToReadable("continue_next_node"),
      content: continueText.value,
      emptyText: "等待继续推理输出",
    };
  }

  return {
    key: "background",
    meta: "background_node",
    kicker: "Background",
    title: nodeNameToReadable("background_node"),
    content: backgroundText.value,
    emptyText: "等待背景信息流入",
  };
});

const isNearNodeScrollBottom = () => {
  const el = nodeScrollEl.value;
  if (!el) return true;
  return el.scrollHeight - el.scrollTop - el.clientHeight < 24;
};

const scrollNodeListToBottom = () => {
  const el = nodeScrollEl.value;
  if (!el) return;
  el.scrollTop = el.scrollHeight;
};

const handleNodeScroll = () => {
  if (nodeScrollFrameId !== null) return;
  nodeScrollFrameId = requestAnimationFrame(() => {
    nodeScrollFrameId = null;
    shouldStickNodeScroll.value = isNearNodeScrollBottom();
  });
};

watch(pendingChoices, (r) => {
  if (choiceItems.value.length) {
    choiceDialogVisible.value = true;
  }
});

watch(
  () => nodeMessages.value.length,
  async () => {
    await nextTick();
    if (shouldStickNodeScroll.value) {
      scrollNodeListToBottom();
    }
  }
);

watch(backgroundText, (value, previousValue) => {
  if (value && value !== previousValue) {
    selectedStreamKey.value = "background";
  }
});

watch(continueText, (value, previousValue) => {
  if (value && value !== previousValue) {
    selectedStreamKey.value = "continue";
  }
});

watch(roleMessages, (msgs) => {
  if (msgs.length > 0) {
/*     console.log("Received role messages:", msgs); */
  }
});

onBeforeUnmount(() => {
  if (nodeScrollFrameId !== null) {
    cancelAnimationFrame(nodeScrollFrameId);
    nodeScrollFrameId = null;
  }
});

</script>

<style scoped>
.interaction-page {
  margin: 0;
/* background-image: url(./assets/background4.png); */
  background-size: cover;              /* 关键：铺满屏幕，必要时裁切 */
  background-repeat: no-repeat;        /* 不重复 */
  background-position: center center;  /* 居中 */
  background-attachment: fixed;        /* 可选：滚动时固定背景（移动端可能不稳定） */
  background-color: #cacaca61;           /* 图片加载前的兜底背景色 */
}
.interaction-page {
  min-height: 100vh;
  padding: 42px 16px 56px;
  box-sizing: border-box;
}

.page-shell {
  max-width: 1920px;
  margin: 0 auto;
  display: grid;
  grid-template-columns: 404px minmax(520px, 1fr) 390px;
  gap: 40px;
  align-items: start;
}

.lane {
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.lane-left,
.lane-center {
  border-right: 1px solid rgba(60, 48, 30, 0.12);
  padding-right: 28px;
}

.lane-right {
  padding-left: 6px;
}

.lane-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 18px;
  padding-bottom: 18px;
  margin-bottom: 24px;
  border-bottom: 1px solid rgba(60, 48, 30, 0.1);
}

.lane-head-center {
  margin-bottom: 30px;
}

.lane-heading {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.lane-kicker,
.stream-kicker {
  font-family: ui-monospace, SFMono-Regular, monospace;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #b6ab9a;
}

.lane-title,
.stream-title {
  margin: 0;
  color: #3d3529;
  font-family: "PingFang SC", "Hiragino Sans GB", "Noto Sans SC", sans-serif;
}

.lane-title {
  font-size: 19px;
  font-weight: 600;
  line-height: 1.35;
}

.stream-title {
  writing-mode: horizontal-tb;
  white-space: nowrap;
  word-break: keep-all;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 14px;
  font-weight: 600;
  line-height: 1.55;
}

.lane-body {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.node-list,
.speech-list {
  gap: 18px;
}

.node-list {
  min-height: 0;
}

.node-scroll {
  --visible-node-count: 5;/* 最多展示节点数量 */
  --node-row-height: 158px;
  flex: 1;
  min-height: 0;
  max-height: calc(var(--visible-node-count) * var(--node-row-height));
  overflow-y: auto;
  overflow-x: hidden;
  padding-right: 6px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  scrollbar-width: thin;
  scrollbar-color: rgba(95, 76, 50, 0.26) transparent;
}

.node-scroll::-webkit-scrollbar {
  width: 6px;
}

.node-scroll::-webkit-scrollbar-track {
  background: transparent;
}

.node-scroll::-webkit-scrollbar-thumb {
  background: rgba(95, 76, 50, 0.22);
  border-radius: 999px;
}

.stream-stack {
  gap: 26px;
}

.stream-switch {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  font-size: 5px;
}

.stream-tab {
  appearance: none;
  min-width: 0;
  border: none;
  border-bottom: 0.5px solid rgba(60, 48, 30, 0.22);
  border-radius: 0;
  background: transparent;
  color: #6f6254;
  padding: 8px 4px 10px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  cursor: pointer;
  transition: border-color 0.2s ease, color 0.2s ease, opacity 0.2s ease;
}

.stream-tab:hover {
  border-bottom-color: rgba(60, 48, 30, 0.34);
}

.stream-tab.active {
  background: transparent;
  border-bottom-color: rgba(95, 76, 50, 0.5);
  color: #3d3529;
}

.stream-tab.populated .stream-tab-kicker::after {
  content: "";
  display: inline-block;
  width: 6px;
  height: 6px;
  margin-left: 8px;
  border-radius: 999px;
  background: #5a7a5e;
  vertical-align: middle;
}

.stream-tab-kicker {
  writing-mode: horizontal-tb;
  font-family: ui-monospace, SFMono-Regular, monospace;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #b6ab9a;
}

.stream-tab-title {
  display: block;
  width: 100%;
  min-width: 0;
  writing-mode: horizontal-tb;
  white-space: nowrap;
  word-break: keep-all;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 14px;
  line-height: 1.5;
  font-weight: 600;
  text-align: left;
  color: inherit;
  font-family: "PingFang SC", "Hiragino Sans GB", "Noto Sans SC", sans-serif;
}

.stream-stage {
  min-height: 0;
  position: relative;
  overflow: hidden;
  isolation: isolate;
  contain: paint;
}

.stream-section {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.stream-section-single {
  width: 100%;
}

.stream-head {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-left: 12px;
}

.card-slide-enter-active,
.card-slide-leave-active {
  transition:
    transform 0.38s cubic-bezier(0.22, 1, 0.36, 1),
    opacity 0.24s ease,
    filter 0.24s ease;
  will-change: transform, opacity, filter;
}

.card-slide-enter-from {
  opacity: 0;
  filter: blur(1px);
  transform: translateX(34px) scale(0.988);
}

.card-slide-enter-to {
  opacity: 1;
  filter: blur(0);
  transform: translateX(0) scale(1);
}

.card-slide-leave-from {
  opacity: 1;
  filter: blur(0);
  transform: translateX(0) scale(1);
}

.card-slide-leave-to {
  opacity: 0;
  filter: blur(1px);
  transform: translateX(-28px) scale(0.992);
}

.status-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 28px;
  padding: 0 12px;
  border: 1px solid rgba(127, 116, 95, 0.18);
  border-radius: 4px;
  color: #7b6b56;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  background: rgba(255, 255, 255, 0.18);
}

.status-pill.online {
  color: #5a7a5e;
  border-color: rgba(90, 122, 94, 0.24);
}

.status-pill.subtle {
  background: transparent;
}

.reset-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 28px;
  padding: 0 10px;
  border: 1px solid rgba(127, 116, 95, 0.18);
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.18);
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.reset-btn:hover {
  background: rgba(255, 255, 255, 0.35);
  transform: rotate(180deg);
}

.send-btn {
  align-self: flex-start;
  margin-bottom: 10px;
  border: 1.5px solid #3d3529;
  border-radius: 4px;
  background: transparent;
  color: #3d3529;
  padding: 8px 18px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.14em;
  cursor: pointer;
  transition: all 0.2s;
}

.send-btn:hover {
  background: #3d3529;
  color: #faf6ee;
}

.node-row {
  border-radius: 8px;
  transition: background-color 0.2s ease;
}

.node-row.clickable {
  cursor: pointer;
}

.node-row.clickable:hover {
  background: rgba(60, 48, 30, 0.04);
}

.node-row.active {
  background: rgba(60, 48, 30, 0.08);
}

.speech-row {
  padding: 4px 0;
}

.empty-state {
  padding: 30px 24px;
  border: 1px dashed rgba(126, 103, 72, 0.3);
  border-radius: 4px;
  color: #8a7458;
  font-size: 14px;
  line-height: 1.75;
  background: rgba(255, 251, 245, 0.16);
}

.empty-state-large {
  min-height: 290px;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
}

.dialog-mask {
  position: fixed;
  inset: 0;
  background-color: rgba(0, 0, 0, 0.718);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
  padding: 16px;
  box-sizing: border-box;
}

.dialog-container {
  width: min(1200px, calc(100vw - 32px));
  box-sizing: border-box;
}

.dialog-single {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.dialog-center {
  display: flex;
  justify-content: center;
}

.dialog-stack {
  width: 100%;
  max-width: 100%;
  display: flex;
  flex-direction: row;
  flex-wrap: nowrap;
  align-items: stretch;
  gap: 24px;
  justify-content: center;
  overflow-x: auto;
  padding: 20px;
  box-sizing: border-box;
}
.dialog-stack > * {
  flex: 0 0 min(380px, 85vw);
}
.dialog-fallback {
  width: min(560px, 100%);
  padding: 24px;
  border: 1px solid rgba(60, 48, 30, 0.08);
  border-radius: 4px;
  background: #fafaf7;
}

.close-btn {
  align-self: center;
  margin-top: 4px;
  min-height: 32px;
  padding: 6px 14px;
  background: rgba(249, 245, 238, 0.96);
  border: 1px solid rgba(60, 48, 30, 0.18);
  border-radius: 3px;
  cursor: pointer;
  color: #6f6254;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  transition:
    background-color 0.2s ease,
    border-color 0.2s ease,
    color 0.2s ease,
    transform 0.15s ease;
}

.close-btn:hover {
  background: #f2e7d8;
  border-color: rgba(60, 48, 30, 0.3);
  color: #3d3529;
}

.close-btn:active {
  transform: translateY(1px);
}

@media (max-width: 1480px) {
  .page-shell {
    grid-template-columns: 368px minmax(440px, 1fr) 340px;
    gap: 32px;
  }

  .lane-left,
  .lane-center {
    padding-right: 22px;
  }

  .stream-switch {
    gap: 12px;
  }
}

@media (max-width: 1180px) {
  .interaction-page {
    padding: 24px 16px 32px;
  }

  .page-shell {
    grid-template-columns: 1fr;
    gap: 28px;
  }

  .lane-left,
  .lane-center {
    border-right: none;
    padding-right: 0;
  }

  .lane-right {
    padding-left: 0;
  }

  .lane-head,
  .lane-head-center {
    margin-bottom: 20px;
  }

  .stream-stack {
    gap: 34px;
  }

  .node-scroll {
    --node-row-height: 150px;
    max-height: calc(var(--visible-node-count) * var(--node-row-height));
  }

  .stream-switch {
    grid-template-columns: 1fr;
  }

  .empty-state-large {
    min-height: 220px;
  }
}
</style>
