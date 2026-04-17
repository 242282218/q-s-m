// @vitest-environment happy-dom

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createApp, defineComponent, nextTick, ref } from 'vue';

const apiMocks = vi.hoisted(() => ({
  getPersonPageData: vi.fn(),
}));

const toastPush = vi.hoisted(() => vi.fn());

vi.mock('@/api', () => ({
  getPersonPageData: apiMocks.getPersonPageData,
}));

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({
    push: toastPush,
  }),
}));

import PersonPage from '@/pages/PersonPage.vue';
import type { PersonCredit, PersonData, PosterCard } from '@/types/api';

function ok<T>(data: T) {
  return {
    code: 0,
    message: '',
    data,
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

function createPosterCard(id: number, title: string): PosterCard {
  return {
    id,
    media_type: 'movie',
    title,
    subtitle: `${2000 + id}`,
    overview: `${title} overview`,
    genres: [18],
    tone: 'warm',
    poster_url: null,
    backdrop_url: null,
  };
}

function createCredit(id: number, title: string): PersonCredit {
  return {
    id,
    media_type: 'movie',
    title,
    year: `${2000 + id}`,
    role: 'Actor',
  };
}

function createPersonData(overrides: Partial<PersonData> = {}): PersonData {
  return {
    id: 7,
    name: 'Sigourney Weaver',
    known_for: 'Acting',
    biography: 'An actor known for science fiction classics.',
    birthday: '1949-10-08',
    place_of_birth: 'New York, USA',
    profile_url: null,
    top_credits: [createPosterCard(1, 'Alien'), createPosterCard(2, 'Aliens')],
    all_credits: Array.from({ length: 12 }, (_, index) =>
      createCredit(index + 1, `Credit ${index + 1}`)
    ),
    ...overrides,
  };
}

async function flushUi() {
  await nextTick();
  await Promise.resolve();
  await new Promise((resolve) => window.setTimeout(resolve, 0));
  await nextTick();
}

describe('PersonPage', () => {
  let host: HTMLDivElement | null = null;
  let cleanup: (() => void) | null = null;

  beforeEach(() => {
    host = document.createElement('div');
    document.body.appendChild(host);

    toastPush.mockReset();
    apiMocks.getPersonPageData.mockReset();
    apiMocks.getPersonPageData.mockResolvedValue(ok(createPersonData()));
  });

  afterEach(() => {
    cleanup?.();
    cleanup = null;
    host?.remove();
    host = null;
    document.body.innerHTML = '';
    vi.clearAllMocks();
  });

  async function mountPersonPage(initialPersonId = 7) {
    const personId = ref(initialPersonId);

    const Root = defineComponent({
      components: { PersonPage },
      setup() {
        return { personId };
      },
      template: '<PersonPage :person-id="personId" />',
    });

    const app = createApp(Root);
    app.mount(host!);
    cleanup = () => app.unmount();
    await flushUi();
    await flushUi();

    return { personId };
  }

  it('renders top credits and splits overflow credits into the collapsed section', async () => {
    await mountPersonPage();

    const creditLists = host!.querySelectorAll('.credits-list');
    const visibleRows = creditLists[0]?.querySelectorAll('.credit-row');
    const hiddenRows = creditLists[1]?.querySelectorAll('.credit-row');

    expect(host!.textContent).toContain('Sigourney Weaver');
    expect(host!.textContent).toContain('代表作');
    expect(host!.textContent).toContain('Alien');
    expect(host!.textContent).toContain('展开全部 2 部作品');
    expect(visibleRows).toHaveLength(10);
    expect(hiddenRows).toHaveLength(2);
  });

  it('ignores late person responses and clears stale content on invalid params', async () => {
    const firstLoad = deferred<ReturnType<typeof ok<PersonData>>>();

    apiMocks.getPersonPageData
      .mockImplementationOnce(() => firstLoad.promise)
      .mockResolvedValueOnce(
        ok(
          createPersonData({
            id: 8,
            name: 'Carrie Fisher',
            top_credits: [createPosterCard(3, 'Star Wars')],
            all_credits: Array.from({ length: 3 }, (_, index) =>
              createCredit(index + 20, `Fisher Credit ${index + 1}`)
            ),
          })
        )
      );

    const state = await mountPersonPage();

    state.personId.value = 8;
    await flushUi();
    await flushUi();

    expect(host!.textContent).toContain('Carrie Fisher');
    expect(host!.textContent).not.toContain('Sigourney Weaver');

    firstLoad.resolve(ok(createPersonData()));
    await flushUi();
    await flushUi();

    expect(host!.textContent).toContain('Carrie Fisher');
    expect(host!.textContent).not.toContain('Sigourney Weaver');

    state.personId.value = 0;
    await flushUi();
    await flushUi();

    expect(host!.textContent).toContain('人物信息加载失败');
    expect(host!.textContent).not.toContain('Carrie Fisher');
    expect(toastPush).toHaveBeenCalledWith('无效的人物参数', 'error');
  });
});
